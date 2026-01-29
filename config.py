import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    # Telegram API (Userbot accounts)
    API_ID: int = int(os.environ.get("API_ID", "0"))
    API_HASH: str = os.environ.get("API_HASH", "")

    # Bot token (service bot)
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")

    # Admin (your Telegram user id)
    ADMIN_ID: int = int(os.environ.get("ADMIN_ID", "0"))

    # Database
    MONGODB_URI: str = os.environ.get("MONGODB_URI", "")  # optional
    SQLITE_PATH: str = os.environ.get("SQLITE_PATH", "app.db")

    # Pricing
    PRICE_WEEK_BDT: int = int(os.environ.get("PRICE_WEEK_BDT", "74"))

    # Web
    PUBLIC_BASE_URL: str = os.environ.get("PUBLIC_BASE_URL", "")  # optional (Render URL)

    # Security note: production-এ session string encrypt করা উচিত
    # এখানে brevity-এর জন্য plain রাখা হয়েছে। চাইলে পরে encryption যোগ করে দেব।
    ENV: str = os.environ.get("ENV", "prod")

settings = Settings()

def require_env_ok():
    missing = []
    if not settings.API_ID:
        missing.append("API_ID")
    if not settings.API_HASH:
        missing.append("API_HASH")
    if not settings.BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not settings.ADMIN_ID:
        missing.append("ADMIN_ID")

    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
