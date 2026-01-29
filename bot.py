import asyncio
import re
from pyrogram import Client, filters
from pyrogram.types import Message

from config import settings
from database import Database, now_ts
from userbot_manager import UserbotManager

from modules.start import start_keyboard, start_text
from modules.pricing import pricing_text
from modules.login import login_instructions
from modules.dashboard import dashboard_text
from modules.billing import buy_text, forwarded_caption
from modules.admin import parse_approve, approved_text
from modules.automation import help_text


class ServiceBot:
    def __init__(self, db: Database, userbots: UserbotManager):
        self.db = db
        self.userbots = userbots
        self.app = Client(
            name="service_bot",
            api_id=settings.API_ID,
            api_hash=settings.API_HASH,
            bot_token=settings.BOT_TOKEN,
            in_memory=True,
        )

    async def start(self):
        await self.app.start()
        me = await self.app.get_me()
        await self.db.add_log(0, "INFO", f"Bot started: @{me.username}")
        self._register_handlers()

    async def stop(self):
        await self.app.stop()

    def _register_handlers(self):
        @self.app.on_message(filters.command("start"))
        async def _start(_, m: Message):
            await self.db.upsert_user(m.from_user.id, m.from_user.username or "")
            await m.reply_text(
                start_text(settings.PRICE_WEEK_BDT),
                reply_markup=start_keyboard(),
                disable_web_page_preview=True
            )

        @self.app.on_callback_query()
        async def _cb(_, q):
            uid = q.from_user.id
            await self.db.upsert_user(uid, q.from_user.username or "")
            data = q.data or ""

            if data == "cb_pricing":
                await q.message.edit_text(pricing_text(settings.PRICE_WEEK_BDT), disable_web_page_preview=True)
            elif data == "cb_login":
                await q.message.edit_text(login_instructions(), disable_web_page_preview=True)
            elif data == "cb_dashboard":
                u = await self.db.get_user(uid) or {}
                prem_ok, prem_until = await self.db.is_premium_active(uid)
                sess = await self.db.get_session(uid)
                cfg = await self.db.get_config(uid)
                await q.message.edit_text(
                    dashboard_text(uid, u.get("username",""), prem_ok, prem_until, bool(sess), len(cfg.get("allow_chats", []))),
                    disable_web_page_preview=True
                )
            elif data == "cb_buy":
                await q.message.edit_text(buy_text(), disable_web_page_preview=True)

            await q.answer()

        @self.app.on_message(filters.command("pricing"))
        async def _pricing(_, m: Message):
            await self.db.upsert_user(m.from_user.id, m.from_user.username or "")
            await m.reply_text(pricing_text(settings.PRICE_WEEK_BDT))

        @self.app.on_message(filters.command("dashboard"))
        async def _dash(_, m: Message):
            uid = m.from_user.id
            await self.db.upsert_user(uid, m.from_user.username or "")
            u = await self.db.get_user(uid) or {}
            prem_ok, prem_until = await self.db.is_premium_active(uid)
            sess = await self.db.get_session(uid)
            cfg = await self.db.get_config(uid)
            await m.reply_text(dashboard_text(uid, u.get("username",""), prem_ok, prem_until, bool(sess), len(cfg.get("allow_chats", []))))

        @self.app.on_message(filters.command("login"))
        async def _login(_, m: Message):
            await self.db.upsert_user(m.from_user.id, m.from_user.username or "")
            await m.reply_text(login_instructions(), disable_web_page_preview=True)

        @self.app.on_message(filters.command("connect"))
        async def _connect(_, m: Message):
            uid = m.from_user.id
            await self.db.upsert_user(uid, m.from_user.username or "")
            parts = m.text.split(maxsplit=1)
            if len(parts) < 2 or len(parts[1].strip()) < 30:
                await m.reply_text("❌ ব্যবহার: `/connect <SESSION_STRING>`", quote=True)
                return
            sess = parts[1].strip()
            await self.db.set_session(uid, sess)
            await self.db.add_log(uid, "INFO", "Session connected by user")
            # Try start userbot once to verify
            app = await self.userbots.ensure_client(uid)
            if app:
                await m.reply_text("✅ Session connected! এখন /dashboard দেখুন।")
            else:
                await m.reply_text("⚠️ Session saved, কিন্তু connect test failed. API_ID/API_HASH ঠিক আছে কিনা দেখুন।")

        # -------- Billing: forward payment proofs to admin --------
        @self.app.on_message(filters.private & (filters.photo | filters.document))
        async def _payment_proof(_, m: Message):
            uid = m.from_user.id
            await self.db.upsert_user(uid, m.from_user.username or "")
            # Forward everything to admin (manual review)
            try:
                cap = forwarded_caption(uid, m.from_user.username or "")
                await m.forward(settings.ADMIN_ID)
                await self.app.send_message(settings.ADMIN_ID, cap)
                await self.db.add_log(uid, "INFO", "Payment proof forwarded to admin")
                await m.reply_text("✅ আপনার পেমেন্ট রিকুয়েস্ট Admin-এর কাছে গেছে। Verify হলে premium চালু হবে।")
            except Exception as e:
                await self.db.add_log(uid, "ERROR", f"Forward failed: {e}")
                await m.reply_text("❌ Forward করতে সমস্যা হয়েছে। পরে আবার চেষ্টা করুন।")

        # -------- Admin approve --------
        @self.app.on_message(filters.user(settings.ADMIN_ID) & filters.command("approve"))
        async def _approve(_, m: Message):
            parsed = parse_approve(m.text)
            if not parsed:
                await m.reply_text("❌ ব্যবহার: `/approve user_id 7_days`")
                return
            user_id, seconds = parsed
            until = max(now_ts(), now_ts()) + int(seconds)
            await self.db.set_premium(user_id, until)
            await self.db.add_log(user_id, "INFO", "Premium approved by admin", {"until": until})
            await m.reply_text(approved_text(user_id, until))
            try:
                await self.app.send_message(user_id, f"✅ Premium activated until {until}. এখন আপনি /dashboard দেখতে পারেন।")
            except Exception:
                pass

        # -------- Automation commands --------
        @self.app.on_message(filters.command("help"))
        async def _help(_, m: Message):
            await m.reply_text(help_text())

        # --- IMPORTANT UPDATE: Restart logic added here ---
        @self.app.on_message(filters.command("allow"))
        async def _allow(_, m: Message):
            uid = m.from_user.id
            await self.db.upsert_user(uid, m.from_user.username or "")
            parts = m.text.split(maxsplit=1)
            if len(parts) < 2:
                await m.reply_text("❌ ব্যবহার: `/allow -100xxxxxxxxxx`")
                return
            try:
                chat_id = int(parts[1].strip())
            except Exception:
                await m.reply_text("❌ chat_id সংখ্যা হতে হবে (যেমন -100...)")
                return
            
            # DB Update
            cfg = await self.db.get_config(uid)
            allow = set(int(x) for x in cfg.get("allow_chats", []))
            allow.add(chat_id)
            await self.db.set_allow_chats(uid, sorted(list(allow)))
            await self.db.add_log(uid, "INFO", "Allow chat added", {"chat_id": chat_id})
            
            # --- RESTART CLIENT TO APPLY NEW TARGET GROUP ---
            # এটি আপনার userbot_manager.py এর নতুন restart_client মেথড কল করবে
            await m.reply_text(f"✅ Added allow chat: `{chat_id}`\n♻️ Restarting monitor to apply changes...")
            
            try:
                # যদি userbot_manager.py এ restart_client না থাকে, তবে ensure_client কল হবে
                if hasattr(self.userbots, 'restart_client'):
                    await self.userbots.restart_client(uid)
                else:
                    # Fallback if method missing (though you should add it to manager)
                    await self.userbots.ensure_client(uid)
            except Exception as e:
                await self.db.add_log(uid, "ERROR", f"Restart failed: {e}")

        @self.app.on_message(filters.command("allowlist"))
        async def _allowlist(_, m: Message):
            uid = m.from_user.id
            cfg = await self.db.get_config(uid)
            allow = cfg.get("allow_chats", [])
            if not allow:
                await m.reply_text("ℹ️ Allowlist empty. /allow দিয়ে যোগ করুন।")
                return
            await m.reply_text("✅ Allowlist:\n" + "\n".join([f"• `{x}`" for x in allow]))

        @self.app.on_message(filters.command("settpl"))
        async def _settpl(_, m: Message):
            uid = m.from_user.id
            await self.db.upsert_user(uid, m.from_user.username or "")
            parts = m.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await m.reply_text("❌ ব্যবহার: `/settpl আপনার টেমপ্লেট টেক্সট`")
                return
            cfg = await self.db.get_config(uid)
            templates = cfg.get("templates", [])
            templates.append({"text": parts[1].strip()})
            await self.db.set_templates(uid, templates)
            await self.db.add_log(uid, "INFO", "Template added", {"count": len(templates)})
            await m.reply_text(f"✅ Template added. Total: {len(templates)}")

        @self.app.on_message(filters.command("post"))
        async def _post(_, m: Message):
            uid = m.from_user.id
            parts = m.text.split()
            if len(parts) < 3:
                await m.reply_text("❌ ব্যবহার: `/post -100xxxxxxxxxx 0`")
                return
            chat_id = int(parts[1])
            idx = int(parts[2])
            ok = await self.userbots.post_template(uid, chat_id, idx)
            await m.reply_text("✅ Posted" if ok else "❌ Blocked/Failed (premium/admin/allowlist check)")

        @self.app.on_message(filters.command("schedule"))
        async def _schedule(_, m: Message):
            uid = m.from_user.id
            parts = m.text.split()
            if len(parts) < 4:
                await m.reply_text("❌ ব্যবহার: `/schedule -100xxxxxxxxxx 0 3600`")
                return
            chat_id = int(parts[1])
            idx = int(parts[2])
            seconds = int(parts[3])
            job_id = await self.userbots.schedule_post_in(uid, chat_id, idx, seconds)
            await m.reply_text(f"✅ Scheduled. Job ID: `{job_id}`")


async def run_service_bot(db: Database, userbots: UserbotManager):
    bot = ServiceBot(db, userbots)
    await bot.start()
    return bot
