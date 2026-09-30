import os
import secrets
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
FLASK_SECRET = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
DATABASE_PATH = os.getenv("DATABASE_PATH", "honeypot.db")
LOCKDOWN_FILE = os.getenv("LOCKDOWN_FILE", "lockdown.flag")
