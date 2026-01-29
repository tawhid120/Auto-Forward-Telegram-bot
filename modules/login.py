def login_instructions() -> str:
    return (
        "🔐 **Login / Connect Session**\n\n"
        "Security reasons-এ আমরা server-এ আপনার SMS/2FA কোড সংগ্রহ করি না।\n\n"
        "✅ Recommended flow:\n"
        "1) আপনার PC/Termux-এ Pyrogram session string generate করুন\n"
        "2) তারপর এখানে পাঠান:  `/connect <SESSION_STRING>`\n\n"
        "Session generator (local) example:\n"
        "```bash\n"
        "pip install pyrogram tgcrypto\n"
        "python -c \"from pyrogram import Client; "
        "api_id=int(input('API_ID: ')); api_hash=input('API_HASH: '); "
        "with Client('gen', api_id=api_id, api_hash=api_hash) as app: "
        "print(app.export_session_string())\"\n"
        "```\n\n"
        "⚠️ কখনও session string অন্য কাউকে দেবেন না।"
    )
