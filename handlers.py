from __future__ import annotations

import asyncio
import logging
import random
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Poll,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest

import database as db
from config import ADMIN_IDS, SUBJECTS_DIR, TIMEOUT_PER_QUESTION
from parser import list_subjects, load_subject

log = logging.getLogger(__name__)


# ---------- helpers ----------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def main_menu_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📝 Test boshlash", callback_data="menu:start")],
        [InlineKeyboardButton("📊 Mening natijalarim", callback_data="menu:my")],
        [InlineKeyboardButton("🏆 Top natijalar", callback_data="menu:top")],
        [InlineKeyboardButton("ℹ️ Bot haqida", callback_data="menu:about")],
    ]
    if is_admin(user_id):
        rows.append([InlineKeyboardButton("👑 Admin panel", callback_data="admin:home")])
    return InlineKeyboardMarkup(rows)


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Bosh menyu", callback_data="menu:home")]]
    )


def escape_md(text: str) -> str:
    # We use plain text everywhere — but if a question has special chars,
    # they are safe because we do NOT use ParseMode by default.
    return text


# ---------- helpers for chat type ----------

def _is_group(chat) -> bool:
    return chat and chat.type in ("group", "supergroup")


async def _show_subject_picker(message, is_group: bool) -> None:
    subjects = list_subjects()
    if not subjects:
        await message.reply_text("⚠️ Hozircha fanlar mavjud emas.")
        return
    rows = []
    for name, path in subjects:
        rows.append([InlineKeyboardButton(f"📘 {name}", callback_data=f"subj:{path.stem}")])
    text = (
        "📚 *Guruh kvizini boshlash uchun fan tanlang:*"
        if is_group
        else "📚 Fanni tanlang:"
    )
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN)


# ---------- /start ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    db.upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")

    if _is_group(chat):
        text = (
            f"👋 *Test Bot guruhda!*\n\n"
            f"Bu yerda guruh kvizini o'tkazasiz — barcha a'zolar qatnashadi.\n\n"
            f"Boshlash uchun /quiz buyrug'ini yuboring."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    text = (
        f"Assalomu alaykum, *{user.first_name}*! 👋\n\n"
        f"📚 Bu — *Test Bot*.\n\n"
        f"Pastdagi tugmalardan birini tanlang:"
    )
    await update.message.reply_text(
        text,
        reply_markup=main_menu_kb(user.id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a quiz — works in both private and group chats."""
    user = update.effective_user
    chat = update.effective_chat
    db.upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")

    state = context.chat_data.get("test")
    if state:
        await update.message.reply_text(
            "⚠️ Bu chatda allaqachon faol test bor. To'xtatish uchun /cancel."
        )
        return

    await _show_subject_picker(update.message, _is_group(chat))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *Yordam*\n\n"
        "/start — Bosh menyu\n"
        "/quiz — Yangi test boshlash (guruhda ham ishlaydi)\n"
        "/cancel — Joriy testni bekor qilish\n\n"
        f"Har bir savolga *{TIMEOUT_PER_QUESTION} sekund* vaqt beriladi.\n\n"
        "👥 *Guruh rejimi:* Botni guruhga qo'shing, /quiz yuboring — barcha a'zolar qatnashishi mumkin."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _is_group(update.effective_chat):
        await update.message.reply_text("Guruhda menyu yo'q. /quiz yuboring.")
        return
    user = update.effective_user
    await update.message.reply_text(
        "Bosh menyu:",
        reply_markup=main_menu_kb(user.id),
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat = update.effective_chat
    state = context.chat_data.get("test")

    if not state:
        await update.message.reply_text("Hozir faol test yo'q.")
        return

    if _is_group(chat):
        if state.get("starter_user_id") != user_id:
            try:
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ("administrator", "creator"):
                    await update.message.reply_text(
                        "⛔ Faqat testni boshlagan kishi yoki guruh admini to'xtata oladi."
                    )
                    return
            except Exception:
                await update.message.reply_text("⛔ Ruxsat tekshirib bo'lmadi.")
                return

    total = len(state["questions"])
    stopped_early = state["idx"] < total
    await _finalize(context, context.chat_data, show_results=True, stopped_early=stopped_early)


# ---------- menu callbacks ----------

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data.split(":", 1)[1]
    user = update.effective_user

    if data == "home":
        await q.edit_message_text(
            "Bosh menyu:",
            reply_markup=main_menu_kb(user.id),
        )
    elif data == "start":
        await _show_subjects(q)
    elif data == "my":
        await _show_my_results(q, user.id)
    elif data == "top":
        await _show_top(q)
    elif data == "about":
        await q.edit_message_text(
            "ℹ️ *Bot haqida*\n\n"
            "Bu bot turli fanlar bo'yicha test topshirish uchun yaratilgan.\n\n"
            f"• Har savol uchun {TIMEOUT_PER_QUESTION} sekund vaqt\n"
            "• Natijalar saqlanadi va top natijalar reytingi yuritiladi\n"
            "• Adminlar yangi fan qo'shishi mumkin",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )


async def _show_subjects(q) -> None:
    subjects = list_subjects()
    if not subjects:
        await q.edit_message_text(
            "⚠️ Hozircha fanlar mavjud emas. Admin qo'shishini kuting.",
            reply_markup=back_kb(),
        )
        return
    rows = []
    for name, path in subjects:
        rows.append([InlineKeyboardButton(f"📘 {name}", callback_data=f"subj:{path.stem}")])
    rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:home")])
    await q.edit_message_text(
        "📚 Fanni tanlang:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def on_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    stem = q.data.split(":", 1)[1]
    path = SUBJECTS_DIR / f"{stem}.txt"
    if not path.exists():
        await q.edit_message_text("❌ Fan topilmadi.", reply_markup=back_kb())
        return
    questions = load_subject(path)
    if not questions:
        await q.edit_message_text("❌ Bu fanda savollar yo'q.", reply_markup=back_kb())
        return

    display_name = stem.replace("_", " ").replace("-", " ").title()
    text = (
        f"📘 *{display_name}*\n\n"
        f"📝 Savollar soni: *{len(questions)} ta*\n"
        f"⏱ Har savolga: *{TIMEOUT_PER_QUESTION} sekund*\n"
        f"🔀 Savollar tasodifiy tartibda beriladi\n\n"
        f"Tayyormisiz?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ha, boshlash", callback_data=f"begin:{stem}")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:start")],
    ])
    await q.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# ---------- test flow (native Telegram quiz polls; private + group) ----------

# Telegram limits
POLL_QUESTION_MAX = 290
POLL_OPTION_MAX = 95
POLL_EXPLANATION_MAX = 195


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _cancel_timer_jobs(state: dict) -> None:
    for job in state.get("timer_jobs", []):
        try:
            job.schedule_removal()
        except Exception:
            pass
    state["timer_jobs"] = []


def _new_participant(user) -> dict:
    return {
        "name": user.first_name or "User",
        "username": user.username or "",
        "user_id": user.id,
        "correct": 0,
        "wrong": 0,
        "skipped": 0,
        "attempt_id": None,
        "answered_q": set(),
    }


async def on_begin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cq = update.callback_query
    await cq.answer()
    user = update.effective_user
    chat = cq.message.chat
    stem = cq.data.split(":", 1)[1]
    path = SUBJECTS_DIR / f"{stem}.txt"
    questions = load_subject(path)
    if not questions:
        await cq.edit_message_text("❌ Savollar yuklanmadi.")
        return

    await _cancel_current_test(context)

    random.shuffle(questions)
    display_name = stem.replace("_", " ").replace("-", " ").title()
    is_group = _is_group(chat)

    context.chat_data["test"] = {
        "subject": display_name,
        "subject_stem": stem,
        "questions": questions,
        "idx": 0,
        "chat_id": chat.id,
        "is_group": is_group,
        "starter_user_id": user.id,
        "starter_name": user.first_name or "",
        "participants": {},
        "current_poll_id": None,
        "current_q_idx": -1,
        "current_poll_msg_id": None,
        "timer_jobs": [],
    }

    mode_line = (
        "👥 *Guruh rejimi:* barcha a'zolar qatnasha oladi\n"
        if is_group
        else ""
    )
    try:
        await cq.edit_message_text(
            f"🚀 *Test boshlandi!*\n\n"
            f"📘 Fan: *{display_name}*\n"
            f"📝 Savollar: *{len(questions)} ta*\n"
            f"⏱ Har savolga: *{TIMEOUT_PER_QUESTION} sekund*\n"
            f"{mode_line}\n"
            f"To'xtatish: /cancel",
            parse_mode=ParseMode.MARKDOWN,
        )
    except BadRequest:
        pass

    await _send_quiz(context, context.chat_data)


def _control_kb_active() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏸ Pauza", callback_data="ctl:pause"),
        InlineKeyboardButton("⛔ Tugatish", callback_data="ctl:stop"),
    ]])


def _control_kb_paused() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ Davom etish", callback_data="ctl:resume"),
        InlineKeyboardButton("⛔ Tugatish", callback_data="ctl:stop"),
    ]])


async def _send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_data: dict) -> None:
    state = chat_data.get("test")
    if not state:
        return
    if state.get("paused"):
        return
    idx = state["idx"]
    if idx >= len(state["questions"]):
        await _finish_test(context, chat_data)
        return

    q = state["questions"][idx]
    total = len(state["questions"])
    chat_id = state["chat_id"]

    options = [_truncate(t, POLL_OPTION_MAX) for _, t in q.options]
    try:
        correct_idx = next(i for i, (letter, _) in enumerate(q.options) if letter == q.correct)
    except StopIteration:
        correct_idx = 0

    header = f"❓ Savol {idx + 1}/{total}"
    full_q = f"{header}\n\n{q.text.strip()}"

    if len(full_q) > POLL_QUESTION_MAX:
        await context.bot.send_message(chat_id=chat_id, text=full_q)
        poll_question = "Javobni tanlang:"
    else:
        poll_question = full_q

    explanation = _truncate(f"✅ To'g'ri: {q.options[correct_idx][1]}", POLL_EXPLANATION_MAX)

    # Clean up buttons on previous poll (if still showing Pause/Stop)
    prev_msg_id = state.get("current_poll_msg_id")
    if prev_msg_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=prev_msg_id, reply_markup=None
            )
        except Exception:
            pass

    msg = await context.bot.send_poll(
        chat_id=chat_id,
        question=poll_question,
        options=options,
        type=Poll.QUIZ,
        correct_option_id=correct_idx,
        is_anonymous=False,
        open_period=TIMEOUT_PER_QUESTION,
        explanation=explanation,
        reply_markup=_control_kb_active(),
    )

    prev = state.get("current_poll_id")
    if prev:
        context.application.bot_data.get("poll_chat", {}).pop(prev, None)

    state["current_poll_id"] = msg.poll.id
    state["current_q_idx"] = idx
    state["current_poll_msg_id"] = msg.message_id

    context.application.bot_data.setdefault("poll_chat", {})[msg.poll.id] = chat_id

    _cancel_timer_jobs(state)
    job = context.job_queue.run_once(
        _on_quiz_timer_end,
        when=TIMEOUT_PER_QUESTION + 1,
        data={"poll_id": msg.poll.id, "q_idx": idx, "chat_id": chat_id},
        name=f"timer_end_{chat_id}_{idx}",
    )
    state["timer_jobs"].append(job)


async def on_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pa = update.poll_answer
    if not pa:
        return

    poll_chat_map = context.application.bot_data.get("poll_chat", {})
    chat_id = poll_chat_map.get(pa.poll_id)
    if not chat_id:
        return
    chat_data = context.application.chat_data[chat_id]
    state = chat_data.get("test")
    if not state or state.get("current_poll_id") != pa.poll_id:
        return
    if state.get("paused"):
        return

    q_idx = state["current_q_idx"]
    q = state["questions"][q_idx]
    user = pa.user

    chosen_idx = pa.option_ids[0] if pa.option_ids else None
    chosen_letter = (
        q.options[chosen_idx][0]
        if chosen_idx is not None and chosen_idx < len(q.options)
        else None
    )

    db.upsert_user(user.id, user.username or "", user.first_name or "", user.last_name or "")

    p = state["participants"].get(user.id)
    if p is None:
        p = _new_participant(user)
        p["attempt_id"] = db.start_attempt(user.id, state["subject"], len(state["questions"]))
        state["participants"][user.id] = p

    if q_idx in p["answered_q"]:
        return
    p["answered_q"].add(q_idx)

    is_correct = db.record_answer(p["attempt_id"], q.number, chosen_letter, q.correct)
    if is_correct:
        p["correct"] += 1
    else:
        p["wrong"] += 1

    # In private chat, auto-advance once the (only) user has answered.
    if not state["is_group"]:
        _cancel_timer_jobs(state)
        if state["idx"] + 1 >= len(state["questions"]):
            target = _finish_job
        else:
            target = _next_quiz_job
        state["idx"] += 1
        state["current_poll_id"] = None
        job = context.job_queue.run_once(
            target,
            when=2.0,
            data={"chat_id": chat_id},
            name=f"adv_{chat_id}_{q_idx}",
        )
        state["timer_jobs"].append(job)


async def _on_quiz_timer_end(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    chat_id = data["chat_id"]
    poll_id = data["poll_id"]
    q_idx = data["q_idx"]
    chat_data = context.application.chat_data[chat_id]
    state = chat_data.get("test")
    if not state:
        return
    if state.get("paused"):
        return
    if state.get("current_poll_id") != poll_id:
        return
    if state.get("current_q_idx") != q_idx:
        return

    # If nobody answered this question, auto-pause the test
    any_answered = any(q_idx in p["answered_q"] for p in state["participants"].values())
    if not any_answered:
        state["paused"] = True
        msg_id = state.get("current_poll_msg_id")
        if msg_id:
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=msg_id, reply_markup=_control_kb_paused()
                )
            except Exception:
                pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏸ *Hech kim javob bermadi — test pauza qilindi*\n\n"
                f"Joriy savol: *{q_idx + 1} / {len(state['questions'])}*\n\n"
                f"▶️ *Davom etish* bilan davom eting, yoki\n"
                f"⛔ *Tugatish* bilan natijalarni saqlang."
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # At least one answer received — mark non-answerers as skipped, advance
    q = state["questions"][q_idx]
    for uid, p in state["participants"].items():
        if q_idx not in p["answered_q"]:
            db.record_answer(p["attempt_id"], q.number, None, q.correct)
            p["skipped"] += 1
            p["answered_q"].add(q_idx)

    context.application.bot_data.get("poll_chat", {}).pop(poll_id, None)
    state["idx"] += 1
    state["current_poll_id"] = None

    if state["idx"] >= len(state["questions"]):
        await _finalize(context, chat_data, show_results=True)
    else:
        await _send_quiz(context, chat_data)


async def _next_quiz_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    chat_data = context.application.chat_data[chat_id]
    if "test" not in chat_data:
        return
    await _send_quiz(context, chat_data)


async def _finish_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    chat_data = context.application.chat_data[chat_id]
    if "test" not in chat_data:
        return
    await _finish_test(context, chat_data)


async def _finalize(
    context: ContextTypes.DEFAULT_TYPE,
    chat_data: dict,
    show_results: bool = True,
    stopped_early: bool = False,
) -> None:
    """Tear down a running test, save attempts, and (optionally) show results."""
    state = chat_data.pop("test", None)
    if not state:
        return
    _cancel_timer_jobs(state)

    pid = state.get("current_poll_id")
    if pid:
        context.application.bot_data.get("poll_chat", {}).pop(pid, None)

    chat_id = state["chat_id"]
    msg_id = state.get("current_poll_msg_id")
    if msg_id:
        try:
            await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=msg_id, reply_markup=None
            )
        except Exception:
            pass

    for uid, p in state["participants"].items():
        try:
            if p.get("attempt_id"):
                db.finish_attempt(p["attempt_id"])
        except Exception:
            pass

    if not show_results:
        return

    total = len(state["questions"])
    if state["is_group"]:
        await _send_group_results(context, chat_id, state, total, stopped_early)
    else:
        await _send_private_results(context, chat_id, state, total, stopped_early)


# Keep a short alias for backward compatibility within this module
async def _finish_test(context, chat_data):
    await _finalize(context, chat_data, show_results=True)


async def _send_private_results(context, chat_id, state, total, stopped_early: bool = False) -> None:
    if not state["participants"]:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Test to'xtatildi (hech bir savolga javob bermadingiz)."
        )
        return
    _, p = next(iter(state["participants"].items()))
    correct = p["correct"]
    wrong = p["wrong"]
    skipped = p["skipped"]
    answered_total = correct + wrong + skipped
    pct = (correct / total * 100) if total else 0

    if pct >= 90:
        grade, emoji = "🏆 A'lo darajada!", "🎊"
    elif pct >= 75:
        grade, emoji = "🥇 Yaxshi natija", "🎉"
    elif pct >= 60:
        grade, emoji = "🥈 Qoniqarli", "👍"
    elif pct >= 40:
        grade, emoji = "🥉 O'rtacha", "💪"
    else:
        grade, emoji = "📕 Yana harakat qiling", "📚"

    title = "Test to'xtatildi" if stopped_early else "Test yakunlandi!"
    early_line = (
        f"⚠️ Erta to'xtatildi: *{answered_total}/{total}* savolga javob berildi\n\n"
        if stopped_early
        else ""
    )

    rank_line = ""
    try:
        rows = db.top_results(subject=state["subject"], limit=10000)
        for i, r in enumerate(rows, 1):
            if r["user_id"] == p["user_id"]:
                rank_line = f"🏅 Joriy o'rningiz: *{i}* / {len(rows)}\n"
                break
    except Exception:
        pass

    best_line = ""
    try:
        best = db.best_attempt(p["user_id"], subject=state["subject"])
        if best:
            best_pct = (best["correct"] / best["total"] * 100) if best["total"] else 0
            if best["correct"] > correct:
                best_line = f"⭐ Eng yaxshi natijangiz: *{best['correct']}/{best['total']}* ({best_pct:.0f}%)\n"
    except Exception:
        pass

    text = (
        f"{emoji} *{title}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📘 Fan: *{state['subject']}*\n"
        f"{early_line}"
        f"📊 Natija: *{correct}/{total}* ({pct:.1f}%)\n\n"
        f"✅ To'g'ri: {correct}\n"
        f"❌ Noto'g'ri: {wrong}\n"
        f"⏭ O'tkazib yuborilgan: {skipped}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{rank_line}"
        f"{best_line}"
        f"{grade}"
    )
    stem = state.get("subject_stem", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Qayta urinish", callback_data=f"begin:{stem}")],
        [InlineKeyboardButton("🏆 Liderlar", callback_data="menu:top")],
        [InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu:home")],
    ])
    await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN
    )


async def _send_group_results(context, chat_id, state, total, stopped_early: bool = False) -> None:
    parts = state["participants"]
    if not parts:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🏁 *Test to'xtatildi*\n\n📘 Fan: *{state['subject']}*\n\n🤷 Hech kim qatnashmadi.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    ranked = sorted(
        parts.values(),
        key=lambda p: (p["correct"], -(p["wrong"] + p["skipped"])),
        reverse=True,
    )
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 100

    title = "Test to'xtatildi" if stopped_early else "Test yakunlandi!"
    answered_q = state["idx"] if stopped_early else total
    progress_line = (
        f"⚠️ Erta to'xtatildi: *{answered_q}/{total}* savol o'tildi"
        if stopped_early
        else f"📝 Savollar: *{total}*"
    )

    lines = [
        f"🏁 *{title}*",
        f"━━━━━━━━━━━━━━━━━━",
        f"📘 Fan: *{state['subject']}*",
        f"{progress_line}",
        f"👥 Qatnashganlar: *{len(ranked)}*",
        f"━━━━━━━━━━━━━━━━━━",
        f"",
        f"🏆 *Liderlar:*",
    ]
    for i, p in enumerate(ranked):
        pct = (p["correct"] / total * 100) if total else 0
        name = (p["name"] or "User").replace("*", "").replace("_", " ").replace("`", "")
        lines.append(
            f"{medals[i]} *{name}* — {p['correct']}/{total} ({pct:.0f}%)"
        )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Yana o'ynash", callback_data=f"begin:{state['subject_stem']}")],
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )


async def _cancel_current_test(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Silent cleanup — used when a new test is starting and we want to clear
    any leftover state without showing a results screen."""
    state = context.chat_data.get("test")
    if not state:
        return False
    await _finalize(context, context.chat_data, show_results=False)
    return True


# ---------- pause / resume / stop controls ----------

async def _can_control(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict) -> bool:
    user_id = update.effective_user.id
    if not state.get("is_group"):
        return True
    if user_id == state.get("starter_user_id"):
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def on_control(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cq = update.callback_query
    state = context.chat_data.get("test")
    if not state:
        await cq.answer("Faol test yo'q.", show_alert=True)
        return
    if not await _can_control(update, context, state):
        await cq.answer(
            "⛔ Bu tugmani faqat testni boshlagan kishi yoki guruh admini bosishi mumkin.",
            show_alert=True,
        )
        return

    action = cq.data.split(":", 1)[1]
    if action == "pause":
        await _pause_quiz(context, state, cq)
    elif action == "resume":
        await _resume_quiz(context, state, cq)
    elif action == "stop":
        await _stop_quiz(context, state, cq)


async def _pause_quiz(context: ContextTypes.DEFAULT_TYPE, state: dict, cq) -> None:
    if state.get("paused"):
        await cq.answer("Allaqachon pauza")
        return
    await cq.answer("⏸ Pauza qilindi")
    state["paused"] = True
    _cancel_timer_jobs(state)

    chat_id = state["chat_id"]
    msg_id = state.get("current_poll_msg_id")
    if msg_id:
        try:
            await context.bot.stop_poll(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=msg_id, reply_markup=_control_kb_paused()
            )
        except Exception:
            pass

    idx = state["idx"]
    total = len(state["questions"])
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⏸ *Test pauza qilindi*\n\n"
            f"Joriy savol: *{idx + 1} / {total}*\n"
            f"Davom etish uchun yuqoridagi ▶️ tugmasini bosing."
        ),
        parse_mode=ParseMode.MARKDOWN,
    )


async def _resume_quiz(context: ContextTypes.DEFAULT_TYPE, state: dict, cq) -> None:
    if not state.get("paused"):
        await cq.answer()
        return
    await cq.answer("▶️ Davom etmoqda...")
    state["paused"] = False
    # Remove control buttons from the paused poll
    msg_id = state.get("current_poll_msg_id")
    if msg_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=state["chat_id"], message_id=msg_id, reply_markup=None
            )
        except Exception:
            pass
    await _send_quiz(context, context.chat_data)


async def _stop_quiz(context: ContextTypes.DEFAULT_TYPE, state: dict, cq) -> None:
    await cq.answer("⛔ Test to'xtatildi")
    total = len(state["questions"])
    stopped_early = state["idx"] < total
    await _finalize(context, context.chat_data, show_results=True, stopped_early=stopped_early)


# ---------- my results / top ----------

async def _show_my_results(q, user_id: int) -> None:
    attempts = db.get_user_attempts(user_id, limit=10)
    if not attempts:
        await q.edit_message_text(
            "📊 Sizda hali test natijalari yo'q.",
            reply_markup=back_kb(),
        )
        return
    lines = ["📊 *Sizning so'nggi natijalaringiz:*\n"]
    for a in attempts:
        if not a["finished_at"]:
            continue
        pct = (a["correct"] / a["total"] * 100) if a["total"] else 0
        date = a["started_at"][:10]
        lines.append(f"• `{date}` — *{a['subject']}*: {a['correct']}/{a['total']} ({pct:.0f}%)")
    if len(lines) == 1:
        lines.append("Hali tugatilgan testlar yo'q.")
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=back_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def _show_top(q) -> None:
    """Top-level leaderboard menu: pick a subject or view overall."""
    subjects = list_subjects()
    rows = [[InlineKeyboardButton("🌐 Umumiy (barcha fanlar)", callback_data="top:all")]]
    for name, path in subjects:
        rows.append([InlineKeyboardButton(f"📘 {name}", callback_data=f"top:{path.stem}")])
    rows.append([InlineKeyboardButton("⬅️ Bosh menyu", callback_data="menu:home")])
    await q.edit_message_text(
        "🏆 *Liderlar tablosi*\n\nQaysi fan bo'yicha ko'rmoqchisiz?",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode=ParseMode.MARKDOWN,
    )


async def on_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    arg = q.data.split(":", 1)[1]
    user_id = update.effective_user.id

    if arg == "all":
        rows = db.top_results(limit=15)
        title = "🌐 Umumiy liderlar (barcha fanlar)"
        subject_filter = None
    else:
        path = SUBJECTS_DIR / f"{arg}.txt"
        display_name = arg.replace("_", " ").replace("-", " ").title()
        rows = db.top_results(subject=display_name, limit=15)
        title = f"📘 {display_name} — liderlar"
        subject_filter = display_name

    if not rows:
        await q.edit_message_text(
            f"{title}\n\n🤷 Hozircha natijalar yo'q.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:top")
            ]]),
        )
        return

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 12
    lines = [f"🏆 *{title}*", "━━━━━━━━━━━━━━━━━━", ""]

    user_rank = None
    user_entry = None
    for i, r in enumerate(rows, 1):
        pct = (r["correct"] / r["total"] * 100) if r["total"] else 0
        name = r["first_name"] or (f"@{r['username']}" if r["username"] else f"User {r['user_id']}")
        name = name.replace("*", "").replace("_", " ").replace("`", "")
        marker = "👉 " if r["user_id"] == user_id else ""
        subj_suffix = "" if subject_filter else f" · {r['subject']}"
        lines.append(
            f"{medals[i-1] if i <= 15 else '·'} {marker}*{name}*  —  "
            f"{r['correct']}/{r['total']} ({pct:.0f}%){subj_suffix}"
        )
        if r["user_id"] == user_id and user_rank is None:
            user_rank = i
            user_entry = r

    # If user not in top 15, find their best rank
    if user_rank is None:
        all_rows = db.top_results(subject=subject_filter, limit=10000)
        for i, r in enumerate(all_rows, 1):
            if r["user_id"] == user_id:
                user_rank = i
                user_entry = r
                break

    lines.append("━━━━━━━━━━━━━━━━━━")
    if user_entry:
        pct = (user_entry["correct"] / user_entry["total"] * 100) if user_entry["total"] else 0
        lines.append(f"🎯 Sizning eng yaxshi o'rningiz:  *{user_rank}*  ({user_entry['correct']}/{user_entry['total']}, {pct:.0f}%)")
    else:
        lines.append("🎯 Siz hali test topshirmagansiz.")

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Liderlar", callback_data="menu:top"),
            InlineKeyboardButton("🏠 Bosh menyu", callback_data="menu:home"),
        ]]),
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------- admin ----------

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Sizda admin huquqi yo'q.")
        return
    await update.message.reply_text(
        f"👑 *Admin panel*\nUser ID: `{user.id}`",
        reply_markup=_admin_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


def _admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika", callback_data="admin:stats")],
        [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin:users")],
        [InlineKeyboardButton("🏆 Eng yaxshi natijalar", callback_data="admin:top")],
        [InlineKeyboardButton("📚 Fanlar ro'yxati", callback_data="admin:subjects")],
        [InlineKeyboardButton("➕ Yangi fan qo'shish", callback_data="admin:addsubject")],
        [InlineKeyboardButton("📢 Hammaga xabar yuborish", callback_data="admin:broadcast")],
        [InlineKeyboardButton("⬅️ Bosh menyu", callback_data="menu:home")],
    ])


async def on_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    if not is_admin(user.id):
        await q.answer("⛔ Admin emas", show_alert=True)
        return
    await q.answer()
    action = q.data.split(":", 1)[1]

    if action == "home":
        await q.edit_message_text(
            f"👑 *Admin panel*\nUser ID: `{user.id}`",
            reply_markup=_admin_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )

    elif action == "stats":
        s = db.stats_overview()
        per_subj = "\n".join(f"  • {n}: {c} marta" for n, c in s["per_subject"]) or "  (yo'q)"
        text = (
            f"📊 *Statistika*\n\n"
            f"👥 Foydalanuvchilar: *{s['users']}*\n"
            f"📝 Tugatilgan testlar: *{s['attempts']}*\n"
            f"📈 O'rtacha ball: *{s['avg_score']*100:.1f}%*\n\n"
            f"*Fanlar bo'yicha:*\n{per_subj}"
        )
        await q.edit_message_text(text, reply_markup=_admin_back_kb(), parse_mode=ParseMode.MARKDOWN)

    elif action == "users":
        users = db.list_users(limit=30)
        if not users:
            await q.edit_message_text("Foydalanuvchilar yo'q.", reply_markup=_admin_back_kb())
            return
        lines = ["👥 *So'nggi foydalanuvchilar (30 tasi):*\n"]
        for u in users:
            uname = f"@{u['username']}" if u["username"] else "—"
            lines.append(f"• `{u['user_id']}` · {u['first_name'] or '—'} · {uname} · testlar: {u['attempts_count']}")
        await q.edit_message_text("\n".join(lines), reply_markup=_admin_back_kb(), parse_mode=ParseMode.MARKDOWN)

    elif action == "top":
        rows = db.top_results(limit=20)
        if not rows:
            await q.edit_message_text("Natijalar yo'q.", reply_markup=_admin_back_kb())
            return
        lines = ["🏆 *Eng yaxshi natijalar (20):*\n"]
        for i, r in enumerate(rows, 1):
            pct = (r["correct"] / r["total"] * 100) if r["total"] else 0
            name = r["first_name"] or (f"@{r['username']}" if r["username"] else f"#{r['user_id']}")
            lines.append(f"{i}. *{name}* · {r['subject']} · {r['correct']}/{r['total']} ({pct:.0f}%)")
        await q.edit_message_text("\n".join(lines), reply_markup=_admin_back_kb(), parse_mode=ParseMode.MARKDOWN)

    elif action == "subjects":
        subjects = list_subjects()
        if not subjects:
            await q.edit_message_text("Fanlar yo'q.", reply_markup=_admin_back_kb())
            return
        lines = ["📚 *Fanlar:*\n"]
        for name, path in subjects:
            try:
                qs = load_subject(path)
                lines.append(f"• *{name}* — {len(qs)} ta savol · `{path.name}`")
            except Exception as e:
                lines.append(f"• *{name}* — ❌ xato: {e}")
        await q.edit_message_text("\n".join(lines), reply_markup=_admin_back_kb(), parse_mode=ParseMode.MARKDOWN)

    elif action == "addsubject":
        context.user_data["awaiting_subject_file"] = True
        await q.edit_message_text(
            "📤 Yangi fan qo'shish uchun *.txt* faylni yuboring.\n\n"
            "Fayl formati: oddiy matn, savol raqami `1.` bilan boshlanadi, "
            "to'g'ri javob `+` belgisi bilan belgilanadi.\n\n"
            "Fayl nomi fan nomi sifatida ishlatiladi (masalan `matematika.txt`).",
            reply_markup=_admin_back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )

    elif action == "broadcast":
        context.user_data["awaiting_broadcast"] = True
        await q.edit_message_text(
            "📢 Hammaga yubormoqchi bo'lgan xabaringizni yozing.\n\n"
            "Bekor qilish uchun /cancel yuboring.",
            reply_markup=_admin_back_kb(),
        )


def _admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Admin panel", callback_data="admin:home")],
    ])


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle file upload from admin to add a new subject."""
    user = update.effective_user
    if not is_admin(user.id) or not context.user_data.get("awaiting_subject_file"):
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("❌ Faqat .txt fayl qabul qilinadi.")
        return

    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in doc.file_name)
    dest = SUBJECTS_DIR / safe_name
    if dest.exists():
        await update.message.reply_text(f"⚠️ `{safe_name}` allaqachon mavjud. Avval o'chiring yoki nomini o'zgartiring.")
        return

    file = await doc.get_file()
    await file.download_to_drive(custom_path=dest)

    # validate
    try:
        qs = load_subject(dest)
        if not qs:
            dest.unlink()
            await update.message.reply_text("❌ Faylda savol topilmadi. Fayl o'chirildi.")
            return
        context.user_data["awaiting_subject_file"] = False
        await update.message.reply_text(
            f"✅ *{safe_name}* qo'shildi.\nSavollar soni: *{len(qs)}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(user.id),
        )
    except Exception as e:
        dest.unlink(missing_ok=True)
        await update.message.reply_text(f"❌ Faylni o'qib bo'lmadi: {e}")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text — used for admin broadcast."""
    user = update.effective_user
    text = update.message.text or ""

    if context.user_data.get("awaiting_broadcast") and is_admin(user.id):
        context.user_data["awaiting_broadcast"] = False
        user_ids = db.all_user_ids()
        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 *Xabar*\n\n{text}", parse_mode=ParseMode.MARKDOWN)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
        await update.message.reply_text(
            f"✅ Yuborildi: {sent}\n❌ Xato: {failed}",
            reply_markup=main_menu_kb(user.id),
        )
        return

    # default: show menu
    await update.message.reply_text("Bosh menyu:", reply_markup=main_menu_kb(user.id))
