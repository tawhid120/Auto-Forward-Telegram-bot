def pricing_text(price_week: int) -> str:
    return (
        "💳 **Pricing**\n\n"
        f"• Premium: **{price_week} টাকা / সপ্তাহ**\n\n"
        "Premium থাকলে:\n"
        "✅ allowlist chat-এ scheduled/manual post\n"
        "✅ dashboard logs\n\n"
        "Free user:\n"
        "✅ dashboard/status\n"
        "❌ posting/scheduling blocked"
    )
