import time
from database import now_ts

def parse_approve(text: str):
    # /approve user_id 7_days
    parts = text.strip().split()
    if len(parts) < 3:
        return None
    try:
        user_id = int(parts[1])
    except Exception:
        return None
    duration = parts[2].lower()

    if duration.endswith("_days"):
        n = int(duration.split("_")[0])
        return user_id, n * 86400
    if duration.endswith("d"):
        n = int(duration[:-1])
        return user_id, n * 86400

    return None

def approved_text(user_id: int, until: int) -> str:
    return f"✅ Approved user `{user_id}` until `{time.strftime('%Y-%m-%d %H:%M', time.localtime(until))}`"
