import time
import json
from typing import Any, Dict, List, Optional, Tuple

from config import settings

# --- Mongo (preferred) ---
_mongo_ok = False
try:
    from motor.motor_asyncio import AsyncIOMotorClient
    _mongo_ok = True
except Exception:
    _mongo_ok = False

# --- SQLite fallback ---
import aiosqlite


def now_ts() -> int:
    return int(time.time())


class Database:
    """
    Collections / tables:
      users: { user_id, username, created_at, premium_until, is_active }
      sessions: { user_id, session_string, updated_at }
      configs: { user_id, allow_chats: [int], templates: [{text, image?}], updated_at }
      logs: { ts, user_id, level, message, meta }
      payments: { ts, user_id, status, note }
      jobs: { job_id, user_id, chat_id, template_idx, run_at, status }
    """

    def __init__(self):
        self.mode = "mongo" if (settings.MONGODB_URI and _mongo_ok) else "sqlite"
        self._mongo = None
        self._db = None
        self._sqlite = None

    async def connect(self):
        if self.mode == "mongo":
            self._mongo = AsyncIOMotorClient(settings.MONGODB_URI)
            self._db = self._mongo.get_default_database()
            # indexes
            await self._db.users.create_index("user_id", unique=True)
            await self._db.sessions.create_index("user_id", unique=True)
            await self._db.configs.create_index("user_id", unique=True)
            await self._db.jobs.create_index([("user_id", 1), ("run_at", 1)])
            await self._db.logs.create_index([("ts", -1)])
        else:
            self._sqlite = await aiosqlite.connect(settings.SQLITE_PATH)
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS users(
                  user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  created_at INTEGER,
                  premium_until INTEGER,
                  is_active INTEGER
                )
            """)
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS sessions(
                  user_id INTEGER PRIMARY KEY,
                  session_string TEXT,
                  updated_at INTEGER
                )
            """)
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS configs(
                  user_id INTEGER PRIMARY KEY,
                  allow_chats TEXT,
                  templates TEXT,
                  updated_at INTEGER
                )
            """)
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS logs(
                  ts INTEGER,
                  user_id INTEGER,
                  level TEXT,
                  message TEXT,
                  meta TEXT
                )
            """)
            await self._sqlite.execute("""
                CREATE TABLE IF NOT EXISTS jobs(
                  job_id TEXT PRIMARY KEY,
                  user_id INTEGER,
                  chat_id INTEGER,
                  template_idx INTEGER,
                  run_at INTEGER,
                  status TEXT
                )
            """)
            await self._sqlite.commit()

    async def close(self):
        if self.mode == "mongo":
            if self._mongo:
                self._mongo.close()
        else:
            if self._sqlite:
                await self._sqlite.close()

    # ---------------- Users ----------------
    async def upsert_user(self, user_id: int, username: str = ""):
        if self.mode == "mongo":
            await self._db.users.update_one(
                {"user_id": user_id},
                {"$setOnInsert": {"created_at": now_ts()},
                 "$set": {"username": username or "", "is_active": True}},
                upsert=True
            )
        else:
            cur = await self._sqlite.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            if row:
                await self._sqlite.execute(
                    "UPDATE users SET username=?, is_active=1 WHERE user_id=?",
                    (username or "", user_id)
                )
            else:
                await self._sqlite.execute(
                    "INSERT INTO users(user_id, username, created_at, premium_until, is_active) VALUES(?,?,?,?,?)",
                    (user_id, username or "", now_ts(), 0, 1)
                )
            await self._sqlite.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        if self.mode == "mongo":
            return await self._db.users.find_one({"user_id": user_id}, {"_id": 0})
        cur = await self._sqlite.execute(
            "SELECT user_id, username, created_at, premium_until, is_active FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "created_at": row[2],
            "premium_until": row[3],
            "is_active": bool(row[4])
        }

    async def set_premium(self, user_id: int, premium_until: int):
        if self.mode == "mongo":
            await self._db.users.update_one({"user_id": user_id}, {"$set": {"premium_until": premium_until}}, upsert=True)
        else:
            await self._sqlite.execute("UPDATE users SET premium_until=? WHERE user_id=?", (premium_until, user_id))
            await self._sqlite.commit()

    async def is_premium_active(self, user_id: int) -> Tuple[bool, int]:
        u = await self.get_user(user_id)
        if not u:
            return False, 0
        until = int(u.get("premium_until") or 0)
        return (until > now_ts()), until

    # ---------------- Sessions ----------------
    async def set_session(self, user_id: int, session_string: str):
        if self.mode == "mongo":
            await self._db.sessions.update_one(
                {"user_id": user_id},
                {"$set": {"session_string": session_string, "updated_at": now_ts()}},
                upsert=True
            )
        else:
            await self._sqlite.execute(
                "INSERT INTO sessions(user_id, session_string, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET session_string=excluded.session_string, updated_at=excluded.updated_at",
                (user_id, session_string, now_ts())
            )
            await self._sqlite.commit()

    async def get_session(self, user_id: int) -> Optional[str]:
        if self.mode == "mongo":
            doc = await self._db.sessions.find_one({"user_id": user_id}, {"_id": 0, "session_string": 1})
            return doc["session_string"] if doc else None
        cur = await self._sqlite.execute("SELECT session_string FROM sessions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

    async def get_users_with_sessions(self) -> List[int]:
        if self.mode == "mongo":
            cursor = self._db.sessions.find({}, {"_id": 0, "user_id": 1})
            return [d["user_id"] async for d in cursor]
        cur = await self._sqlite.execute("SELECT user_id FROM sessions")
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows]

    # ---------------- Config ----------------
    async def get_config(self, user_id: int) -> Dict[str, Any]:
        default_templates = [
            {"text": "Hello! This is a scheduled update."},
            {"text": "Reminder: Please check the pinned message."}
        ]
        if self.mode == "mongo":
            doc = await self._db.configs.find_one({"user_id": user_id}, {"_id": 0})
            if not doc:
                return {"user_id": user_id, "allow_chats": [], "templates": default_templates}
            doc.setdefault("allow_chats", [])
            doc.setdefault("templates", default_templates)
            return doc

        cur = await self._sqlite.execute("SELECT allow_chats, templates FROM configs WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return {"user_id": user_id, "allow_chats": [], "templates": default_templates}
        allow_chats = json.loads(row[0] or "[]")
        templates = json.loads(row[1] or "[]") or default_templates
        return {"user_id": user_id, "allow_chats": allow_chats, "templates": templates}

    async def set_allow_chats(self, user_id: int, allow_chats: List[int]):
        cfg = await self.get_config(user_id)
        cfg["allow_chats"] = allow_chats
        await self._upsert_config(user_id, cfg)

    async def set_templates(self, user_id: int, templates: List[Dict[str, Any]]):
        cfg = await self.get_config(user_id)
        cfg["templates"] = templates
        await self._upsert_config(user_id, cfg)

    async def _upsert_config(self, user_id: int, cfg: Dict[str, Any]):
        if self.mode == "mongo":
            await self._db.configs.update_one(
                {"user_id": user_id},
                {"$set": {"allow_chats": cfg.get("allow_chats", []),
                          "templates": cfg.get("templates", []),
                          "updated_at": now_ts()}},
                upsert=True
            )
        else:
            await self._sqlite.execute(
                "INSERT INTO configs(user_id, allow_chats, templates, updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET allow_chats=excluded.allow_chats, templates=excluded.templates, updated_at=excluded.updated_at",
                (user_id, json.dumps(cfg.get("allow_chats", [])), json.dumps(cfg.get("templates", [])), now_ts())
            )
            await self._sqlite.commit()

    # ---------------- Logs ----------------
    async def add_log(self, user_id: int, level: str, message: str, meta: Optional[Dict[str, Any]] = None):
        meta_s = json.dumps(meta or {}, ensure_ascii=False)
        if self.mode == "mongo":
            await self._db.logs.insert_one({"ts": now_ts(), "user_id": user_id, "level": level, "message": message, "meta": meta or {}})
        else:
            await self._sqlite.execute(
                "INSERT INTO logs(ts, user_id, level, message, meta) VALUES(?,?,?,?,?)",
                (now_ts(), user_id, level, message, meta_s)
            )
            await self._sqlite.commit()

    async def list_logs(self, limit: int = 200) -> List[Dict[str, Any]]:
        limit = max(1, min(1000, int(limit)))
        if self.mode == "mongo":
            cursor = self._db.logs.find({}, {"_id": 0}).sort("ts", -1).limit(limit)
            return [d async for d in cursor]
        cur = await self._sqlite.execute(
            "SELECT ts, user_id, level, message, meta FROM logs ORDER BY ts DESC LIMIT ?",
            (limit,)
        )
        rows = await cur.fetchall()
        out = []
        for r in rows:
            out.append({"ts": r[0], "user_id": r[1], "level": r[2], "message": r[3], "meta": json.loads(r[4] or "{}")})
        return out

    # ---------------- Jobs (simple scheduler) ----------------
    async def add_job(self, job_id: str, user_id: int, chat_id: int, template_idx: int, run_at: int):
        if self.mode == "mongo":
            await self._db.jobs.insert_one({
                "job_id": job_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "template_idx": template_idx,
                "run_at": run_at,
                "status": "pending"
            })
        else:
            await self._sqlite.execute(
                "INSERT INTO jobs(job_id, user_id, chat_id, template_idx, run_at, status) VALUES(?,?,?,?,?,?)",
                (job_id, user_id, chat_id, template_idx, run_at, "pending")
            )
            await self._sqlite.commit()

    async def fetch_due_jobs(self, now: int, limit: int = 50) -> List[Dict[str, Any]]:
        if self.mode == "mongo":
            cursor = self._db.jobs.find({"status": "pending", "run_at": {"$lte": now}}, {"_id": 0}).limit(limit)
            return [d async for d in cursor]
        cur = await self._sqlite.execute(
            "SELECT job_id, user_id, chat_id, template_idx, run_at, status FROM jobs WHERE status='pending' AND run_at<=? LIMIT ?",
            (now, limit)
        )
        rows = await cur.fetchall()
        return [{"job_id": r[0], "user_id": r[1], "chat_id": r[2], "template_idx": r[3], "run_at": r[4], "status": r[5]} for r in rows]

    async def mark_job_done(self, job_id: str):
        if self.mode == "mongo":
            await self._db.jobs.update_one({"job_id": job_id}, {"$set": {"status": "done"}})
        else:
            await self._sqlite.execute("UPDATE jobs SET status='done' WHERE job_id=?", (job_id,))
            await self._sqlite.commit()
