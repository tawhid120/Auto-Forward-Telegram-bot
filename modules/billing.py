def buy_text() -> str:
    return (
        "🛒 **Buy Premium (Manual Verification)**\n\n"
        "পেমেন্ট করে স্ক্রিনশট পাঠান। আমি (Admin) ম্যানুয়ালি verify করে premium চালু করব।\n\n"
        "✅ নির্দেশনা:\n"
        "1) Payment করুন (আপনার পছন্দের মাধ্যমে)\n"
        "2) স্ক্রিনশট এই চ্যাটে পাঠান\n"
        "3) Admin verify করলে premium activate হবে\n\n"
        "⏳ Verify শেষে আপনি /dashboard এ status দেখতে পারবেন।"
    )

def forwarded_caption(user_id: int, username: str) -> str:
    return f"💳 Payment Request\nUser: {user_id} @{username}\nApprove: /approve {user_id} 7_days"
