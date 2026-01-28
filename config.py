import os

class Config:
    API_ID = int(os.environ.get("API_ID", "20193909"))
    API_HASH = os.environ.get("API_HASH", "82cd035fc1eb439bda68b2bfc75a57cb")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "") # @BotFather থেকে পাওয়া টোকেন
    OWNER_ID = int(os.environ.get("OWNER_ID", "0")) # আপনার টেলিগ্রাম ID
    MONGO_URL = os.environ.get("MONGO_URL", "") # MongoDB কানেকশন স্ট্রিং
    # আপনার টার্গেট গ্রুপ এবং ইগনোর লিস্ট
    TARGET_GROUPS = [
        'chemistryteli', 'hsc_sharing', 'linkedstudies', 'hsc234', 
        'buetkuetruetcuet', 'thejournyofhsc24', 'haters_hsc', 'Dacs2025'
    ]
    IGNORED_BOTS = ['MissRose_bot']
