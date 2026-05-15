import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
SUBJECTS_DIR = BASE_DIR / "subjects"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bot.db"

SUBJECTS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

_admin_raw = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = {int(x) for x in _admin_raw.split(",") if x.strip().isdigit()}

TIMEOUT_PER_QUESTION = int(os.getenv("TIMEOUT_PER_QUESTION", "30"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN .env faylda topilmadi")
