from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="cb_dashboard"),
         InlineKeyboardButton("💳 Pricing", callback_data="cb_pricing")],
        [InlineKeyboardButton("🔐 Login (Session)", callback_data="cb_login"),
         InlineKeyboardButton("🛒 Buy Premium", callback_data="cb_buy")],
    ])

def start_text(price_week: int) -> str:
    return (
        "👋 **Welcome to Userbot-as-a-Service**\n\n"
        "এখানে আপনি আপনার নিজের Telegram account (session string) connect করে "
        "শুধু অনুমোদিত গ্রুপ/চ্যানেলে safe automation চালাতে পারবেন।\n\n"
        f"✅ Premium: **{price_week} টাকা / সপ্তাহ**\n"
        "⚠️ Anti-spam policy: allowlist + admin-check ছাড়া automation চলবে না।"
    )
