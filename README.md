# Telegram Test Bot

Professional Telegram quiz bot built on top of Telegram's **native quiz polls** — works in private chats and in groups, with multiple subjects, leaderboards, pause/resume, and an admin panel.

> O'zbek tilida loyiha tavsifi pastda 👇

---

## Features

- 🎯 **Native Telegram quiz polls** — proper UI, automatic timer, instant correct/wrong feedback
- 👥 **Group mode** — all group members can compete; per-session leaderboard
- ⏸ **Pause / Resume / Stop** buttons attached to every quiz poll
- 🤖 **Auto-pause** when no one answers within the timer — the test waits instead of skipping
- 🏆 **Leaderboards** per subject and across all subjects, ranking by each user's **latest** attempt
- 📊 Personal results: your current rank, your all-time best, full breakdown
- 👑 **Admin panel** — statistics, user list, broadcast, upload new subject files via Telegram
- 📚 **Multi-subject** — drop a `.txt` file into `subjects/` (or upload via admin panel) and a new subject appears

---

## Tech stack

- Python 3.10+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21
- SQLite (built into Python)
- python-dotenv

---

## Quick start

```bash
# 1) Clone
git clone https://github.com/<your-username>/telegram-test-bot.git
cd telegram-test-bot

# 2) Create virtual env (optional but recommended)
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate            # Windows PowerShell

# 3) Install dependencies
pip install -r requirements.txt

# 4) Copy env template and fill in your token
cp .env.example .env
# edit .env: paste BOT_TOKEN from @BotFather, set ADMIN_IDS

# 5) Run
python bot.py
```

### Environment variables (`.env`)

| Variable | Description |
| --- | --- |
| `BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Comma-separated Telegram user IDs of admins (use [@userinfobot](https://t.me/userinfobot) to find yours) |
| `TIMEOUT_PER_QUESTION` | Seconds per question (default `30`, must be 5-600) |

---

## Adding a new subject

Drop a `.txt` file into the `subjects/` folder and restart the bot — or upload it via the admin panel from inside Telegram.

### File format

```
1. Question text?
A) Wrong option
+B) Correct option
C) Wrong option
D) Wrong option

2. Another question text?
+A) Correct option
B) Wrong option
C) Wrong option
D) Wrong option
```

- Questions are numbered (`1.`, `2.`, …); the parser is forgiving about gaps
- Options start with `A)`, `B)`, `C)`, `D)`
- Prefix the **correct** option's letter with `+`
- Multi-line question bodies (e.g. code snippets) are supported

The file's name (without extension) becomes the subject's display name. Example: `algebra.txt` → "Algebra".

---

## Bot commands

| Command | What it does |
| --- | --- |
| `/start` | Welcome + main menu (in private chats) |
| `/quiz` | Start a new test — works in private chats **and** in groups |
| `/cancel` | Stop the current test and save partial results to the leaderboard |
| `/help` | Help |
| `/admin` | Open the admin panel (admins only) |

---

## Group quizzes

1. Add the bot to a group
2. Optional but recommended: in [@BotFather](https://t.me/BotFather), run `/setprivacy` → select your bot → **Disable** (lets the bot read group commands)
3. Anyone in the group sends `/quiz`
4. Pick a subject → press **✅ Ha, boshlash**
5. All members can answer each quiz poll
6. After each timer (or when everyone answers), the next question appears automatically
7. At the end, a per-group leaderboard is shown

> The **⏸ Pauza** and **⛔ Tugatish** buttons in a group can only be pressed by the person who started the quiz or by a group administrator.

---

## Project structure

```
telegram-test-bot/
├── bot.py              # entry point — registers handlers and runs the bot
├── handlers.py         # all message / callback / poll-answer handlers
├── parser.py           # parses subject .txt files into Question objects
├── database.py         # SQLite schema and queries
├── config.py           # loads .env and exposes configuration
├── requirements.txt
├── .env.example        # template — copy to .env and fill in
├── subjects/           # one .txt file per subject
│   └── elektronika.txt # sample subject (Uzbek)
└── data/               # auto-created at runtime; SQLite DB lives here
```

---

## How the leaderboard works

The leaderboard shows **one entry per user — their most recent finished attempt** — ordered from highest to lowest score. Retaking the test changes your rank (for better or worse). Use it as a "current standings" board, not a hall of fame.

Each user's all-time personal best is shown separately in their own result screen (`⭐ Eng yaxshi natijangiz: …`).

---

## License

MIT — do what you want, attribution appreciated.

---

# 🇺🇿 O'zbek tilida

**Telegram Test Bot** — Telegram'ning *native quiz poll*lari asosida qurilgan professional test boti. Shaxsiy chatlarda va guruhlarda ishlaydi. Bir necha fan, liderlar tablosi, pauza/davom etish/tugatish tugmalari, hamda admin paneli mavjud.

### Asosiy imkoniyatlar

- 🎯 Native Telegram quiz poll (taymer, javob ko'rsatish — barchasi Telegram tomonidan)
- 👥 Guruh rejimi — barcha a'zolar qatnashadi, oxirida liderlar tablosi
- ⏸ Pauza / ▶️ Davom etish / ⛔ Tugatish tugmalari har bir poll'da
- 🤖 Hech kim javob bermasa — avtomatik pauza (savol o'tkazib yuborilmaydi)
- 🏆 Fan bo'yicha va umumiy liderlar tablosi (har user uchun so'nggi natijasi)
- 📊 Shaxsiy natijalar: hozirgi o'rin, eng yaxshi natija
- 👑 Admin panel: statistika, foydalanuvchilar, ommaviy xabar yuborish, yangi fan qo'shish (Telegram orqali fayl yuborish)
- 📚 Bir nechta fan — `.txt` faylni `subjects/` ga tashlash kifoya

### Yangi fan qo'shish

`subjects/` papkasiga `.txt` fayl tashlang. Format:

```
1. Savol matni?
A) Variant
+B) To'g'ri javob
C) Variant
D) Variant
```

To'g'ri javob `+` belgisi bilan boshlanadi. Fayl nomi fan nomi bo'ladi.

### Buyruqlar

- `/start` — bosh menyu
- `/quiz` — yangi test boshlash (guruhda ham ishlaydi)
- `/cancel` — joriy testni to'xtatish (natijalar saqlanadi)
- `/admin` — admin paneli
- `/help` — yordam

### Guruhga qo'shish

1. Botni guruhga qo'shing
2. [@BotFather](https://t.me/BotFather) → `/setprivacy` → botingiz → **Disable**
3. Guruhda `/quiz` yuboring va fan tanlang
4. Hamma qatnashadi, oxirida reyting chiqadi
