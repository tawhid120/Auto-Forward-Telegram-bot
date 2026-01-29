import asyncio
import random
import os
import logging
from typing import Dict, Optional, List

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait, ChatWriteForbidden

from config import settings
from database import Database

class UserbotManager:
    def __init__(self, db: Database):
        self.db = db
        self.clients: Dict[int, Client] = {}
        # মনিটরিং টাস্ক স্টোর: {user_id: {chat_id: task}}
        self.monitor_tasks: Dict[int, Dict[int, asyncio.Task]] = {}
        
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

        # main (6).py এর কনফিগারেশন
        self.IGNORED_BOTS = ['MissRose_bot', 'GroupHelpBot'] 
        self.DEFAULT_IMAGE = 'gmail.jpg' 

    async def start(self):
        pass # দরকার হলে ব্যাকগ্রাউন্ড জব লুপ এখানে দিতে পারো

    async def stop(self):
        self._stop.set()
        async with self._lock:
            # সব টাস্ক ক্যানসেল
            for uid_tasks in self.monitor_tasks.values():
                for task in uid_tasks.values():
                    task.cancel()
            self.monitor_tasks.clear()

            # সব ক্লায়েন্ট স্টপ
            for c in self.clients.values():
                try:
                    await c.stop()
                except Exception:
                    pass
            self.clients.clear()

    # --- নতুন মেথড: কনফিগ চেঞ্জ হলে রিস্টার্ট করার জন্য ---
    async def restart_client(self, user_id: int):
        async with self._lock:
            if user_id in self.clients:
                try:
                    await self.clients[user_id].stop()
                except:
                    pass
                del self.clients[user_id]
            
            # আগের টাস্ক ক্লিয়ার করা
            if user_id in self.monitor_tasks:
                for t in self.monitor_tasks[user_id].values():
                    t.cancel()
                del self.monitor_tasks[user_id]

        # আবার চালু করা
        await self.ensure_client(user_id)

    async def ensure_client(self, user_id: int) -> Optional[Client]:
        async with self._lock:
            if user_id in self.clients:
                return self.clients[user_id]

            sess = await self.db.get_session(user_id)
            if not sess:
                return None

            app = Client(
                name=f"user_{user_id}",
                api_id=settings.API_ID,
                api_hash=settings.API_HASH,
                session_string=sess,
                in_memory=True, # মেমোরিতে রান হবে ফাস্ট হওয়ার জন্য
            )
            try:
                await app.start()
                self.clients[user_id] = app
                
                # মনিটরিং চালু (main 6.py লজিক)
                await self._start_monitoring(user_id, app)
                
                me = await app.get_me()
                await self.db.add_log(user_id, "INFO", f"Userbot connected: {me.first_name}")
                return app
            except Exception as e:
                await self.db.add_log(user_id, "ERROR", f"Start failed: {e}")
                return None

    async def _start_monitoring(self, user_id: int, app: Client):
        """main (6).py এর লজিক অনুযায়ী গ্রুপ মনিটর"""
        cfg = await self.db.get_config(user_id)
        
        # লক্ষ্য করুন: এখানে allow_chats কেই target_groups হিসেবে ধরা হচ্ছে
        target_groups = cfg.get("allow_chats", []) 
        
        if not target_groups:
            return

        # লিস্টের আইটেমগুলো ইন্টিজার কিনা নিশ্চিত করা
        target_groups = [int(x) for x in target_groups]

        if user_id not in self.monitor_tasks:
            self.monitor_tasks[user_id] = {}

        # হুবহু main (6).py এর incoming_handler
        async def incoming_handler(client, message):
            if self._stop.is_set(): return

            chat_id = message.chat.id
            user = message.from_user

            # ১. ভ্যালিডেশন
            if not user: return
            if user.is_self: return # নিজের মেসেজ ইগনোর
            if user.username in self.IGNORED_BOTS: return # রোজ বট ইগনোর

            # ২. টাইমার রিসেট লজিক (Debounce)
            user_tasks = self.monitor_tasks.get(user_id, {})
            
            if chat_id in user_tasks:
                if not user_tasks[chat_id].done():
                    user_tasks[chat_id].cancel()
            
            # ৩. নতুন ১৫ সেকেন্ডের টাস্ক
            task = asyncio.create_task(self._wait_and_send_ad(user_id, client, chat_id))
            self.monitor_tasks[user_id][chat_id] = task

        # হ্যান্ডলার অ্যাড করা (শুধুমাত্র টার্গেট গ্রুপগুলোর জন্য)
        app.add_handler(MessageHandler(
            incoming_handler,
            filters.chat(target_groups) & ~filters.me
        ))

    async def _wait_and_send_ad(self, user_id: int, app: Client, chat_id: int):
        try:
            await asyncio.sleep(15) # ১৫ সেকেন্ড অপেক্ষা
            await self._send_ad_message(user_id, app, chat_id)
        except asyncio.CancelledError:
            pass # নতুন মেসেজ আসলে ক্যানসেল হবে
        except Exception as e:
            await self.db.add_log(user_id, "ERROR", f"Timer Error: {e}")
        finally:
            if user_id in self.monitor_tasks and chat_id in self.monitor_tasks[user_id]:
                self.monitor_tasks[user_id].pop(chat_id, None)

    async def _send_ad_message(self, user_id: int, app: Client, chat_id: int):
        # ১. প্রিমিয়াম চেক (যদি দরকার হয়)
        ok, _ = await self.db.is_premium_active(user_id)
        if not ok: return

        # ২. টেমপ্লেট লোড
        cfg = await self.db.get_config(user_id)
        templates = cfg.get("templates", [])
        
        if not templates: return

        # ৩. র‍্যান্ডম সিলেকশন
        selection = random.choice(templates)
        
        caption_text = selection.get("text", "")
        # ডিফল্টভাবে DB তে image ফিল্ড নেই, তাই টেক্সট পার্সিং (main 6.py স্টাইল)
        photo_path = None

        # "Image: path/to/img" পার্সিং লজিক
        if caption_text.lower().startswith("image:"):
            parts = caption_text.split("\n", 1)
            if len(parts) > 0:
                potential_path = parts[0].split(":", 1)[1].strip()
                if potential_path:
                    photo_path = potential_path
                    # বাকি অংশ ক্যাপশন
                    caption_text = parts[1] if len(parts) > 1 else ""

        # ৪. সেন্ডিং
        try:
            if photo_path:
                if not os.path.exists(photo_path):
                     photo_path = self.DEFAULT_IMAGE 
                
                await app.send_photo(chat_id, photo=photo_path, caption=caption_text)
            else:
                if caption_text:
                    await app.send_message(chat_id, caption_text)

            await self.db.add_log(user_id, "INFO", f"Ads posted in {chat_id}")

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            await self.db.add_log(user_id, "ERROR", f"Post failed: {e}")

    # ম্যানুয়াল পোস্টিং (অপশনাল)
    async def post_template(self, user_id: int, chat_id: int, idx: int):
        app = await self.ensure_client(user_id)
        if app:
            await self._send_ad_message(user_id, app, chat_id)
            return True
        return False
    
    # শিডিউলিং (অপশনাল - যদি রাখতে চাও)
    async def schedule_post_in(self, *args):
        return "sched_disabled_in_this_version"
