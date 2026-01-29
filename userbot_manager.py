import asyncio
import time
import uuid
from typing import Any, Dict, Optional

from pyrogram import Client
from pyrogram.errors import FloodWait

from config import settings
from database import Database, now_ts


class UserbotManager:
    def __init__(self, db: Database):
        self.db = db
        self.clients: Dict[int, Client] = {}  # user_id -> pyrogram client
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

    async def start(self):
        # start scheduler loop
        asyncio.create_task(self._job_loop(), name="job_loop")

    async def stop(self):
        self._stop.set()
        async with self._lock:
            for uid, c in list(self.clients.items()):
                try:
                    await c.stop()
                except Exception:
                    pass
            self.clients.clear()

    async def ensure_client(self, user_id: int) -> Optional[Client]:
        async with self._lock:
            if user_id in self.clients:
                return self.clients[user_id]

            sess = await self.db.get_session(user_id)
            if not sess:
                return None

            # NOTE: multiি "account name" unique রাখা দরকার
            app = Client(
                name=f"user_{user_id}",
                api_id=settings.API_ID,
                api_hash=settings.API_HASH,
                session_string=sess,
                in_memory=False,
            )
            try:
                await app.start()
                self.clients[user_id] = app
                me = await app.get_me()
                await self.db.add_log(user_id, "INFO", f"Userbot connected: {me.first_name} (@{me.username})", {"tg_id": me.id})
                return app
            except Exception as e:
                await self.db.add_log(user_id, "ERROR", f"Failed to start userbot: {e}")
                try:
                    await app.stop()
                except Exception:
                    pass
                return None

    async def is_chat_allowed_and_admin(self, user_id: int, chat_id: int) -> bool:
        cfg = await self.db.get_config(user_id)
        if int(chat_id) not in [int(x) for x in cfg.get("allow_chats", [])]:
            return False

        app = await self.ensure_client(user_id)
        if not app:
            return False

        try:
            me = await app.get_me()
            member = await app.get_chat_member(chat_id, me.id)
            # admin/owner check
            return member.status in ("administrator", "owner")
        except Exception:
            return False

    async def post_template(self, user_id: int, chat_id: int, template_idx: int = 0) -> bool:
        # premium check
        ok, until = await self.db.is_premium_active(user_id)
        if not ok:
            await self.db.add_log(user_id, "WARN", "Blocked posting: premium inactive", {"premium_until": until})
            return False

        if not await self.is_chat_allowed_and_admin(user_id, chat_id):
            await self.db.add_log(user_id, "WARN", "Blocked posting: chat not allowed or not admin", {"chat_id": chat_id})
            return False

        cfg = await self.db.get_config(user_id)
        templates = cfg.get("templates", [])
        if not templates:
            await self.db.add_log(user_id, "ERROR", "No templates configured")
            return False
        template_idx = max(0, min(int(template_idx), len(templates) - 1))
        t = templates[template_idx]

        app = await self.ensure_client(user_id)
        if not app:
            await self.db.add_log(user_id, "ERROR", "No userbot client available")
            return False

        try:
            # Safe: text-only by default
            text = (t.get("text") or "").strip()
            if not text:
                await self.db.add_log(user_id, "ERROR", "Template text is empty")
                return False

            await app.send_message(chat_id, text)
            await self.db.add_log(user_id, "INFO", "Posted template", {"chat_id": chat_id, "template_idx": template_idx})
            return True

        except FloodWait as e:
            await self.db.add_log(user_id, "WARN", f"FloodWait {e.value}s", {"chat_id": chat_id})
            await asyncio.sleep(e.value)
            return False
        except Exception as e:
            await self.db.add_log(user_id, "ERROR", f"Send failed: {e}", {"chat_id": chat_id})
            return False

    async def schedule_post_in(self, user_id: int, chat_id: int, template_idx: int, seconds: int) -> str:
        run_at = now_ts() + max(5, int(seconds))
        job_id = str(uuid.uuid4())
        await self.db.add_job(job_id, user_id, int(chat_id), int(template_idx), run_at)
        await self.db.add_log(user_id, "INFO", "Job scheduled", {"job_id": job_id, "run_at": run_at, "chat_id": chat_id})
        return job_id

    async def _job_loop(self):
        while not self._stop.is_set():
            try:
                due = await self.db.fetch_due_jobs(now_ts(), limit=30)
                for job in due:
                    uid = int(job["user_id"])
                    chat_id = int(job["chat_id"])
                    idx = int(job["template_idx"])
                    job_id = job["job_id"]

                    await self.post_template(uid, chat_id, idx)
                    await self.db.mark_job_done(job_id)

                await asyncio.sleep(3)
            except Exception:
                await asyncio.sleep(3)
