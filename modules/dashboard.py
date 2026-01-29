import time

def fmt_ts(ts: int) -> str:
    if not ts:
        return "N/A"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

def dashboard_text(user_id: int, username: str, premium_ok: bool, premium_until: int, has_session: bool, allow_count: int) -> str:
    return (
        "📊 **Your Dashboard**\n\n"
        f"• User: `{user_id}` @{username}\n"
        f"• Session: {'✅ Connected' if has_session else '❌ Not connected'}\n"
        f"• Allowlist chats: **{allow_count}**\n"
        f"• Premium: {'✅ Active' if premium_ok else '❌ Inactive'}\n"
        f"• Premium Until: **{fmt_ts(premium_until)}**\n\n"
        "Commands:\n"
        "• /allow -100xxxxxx (add allow chat)\n"
        "• /post -100xxxxxx 0 (post template idx)\n"
        "• /schedule -100xxxxxx 0 3600 (post after seconds)\n"
    )
