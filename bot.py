import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PollAnswerHandler,
    filters,
)

import database as db
import handlers as h
from config import BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


def main() -> None:
    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", h.cmd_start))
    app.add_handler(CommandHandler("menu", h.cmd_menu))
    app.add_handler(CommandHandler("quiz", h.cmd_quiz))
    app.add_handler(CommandHandler("help", h.cmd_help))
    app.add_handler(CommandHandler("cancel", h.cmd_cancel))
    app.add_handler(CommandHandler("admin", h.cmd_admin))

    # Callback queries
    app.add_handler(CallbackQueryHandler(h.on_menu, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(h.on_subject, pattern=r"^subj:"))
    app.add_handler(CallbackQueryHandler(h.on_begin, pattern=r"^begin:"))
    app.add_handler(CallbackQueryHandler(h.on_top, pattern=r"^top:"))
    app.add_handler(CallbackQueryHandler(h.on_timer, pattern=r"^timer:"))
    app.add_handler(CallbackQueryHandler(h.on_admin, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(h.on_control, pattern=r"^ctl:"))

    # Quiz poll answers
    app.add_handler(PollAnswerHandler(h.on_poll_answer))

    # Documents (for admin uploading new subject files)
    app.add_handler(MessageHandler(filters.Document.ALL, h.on_document))

    # Fallback text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h.on_text))

    log.info("Bot ishga tushdi...")
    app.run_polling(allowed_updates=["message", "callback_query", "poll_answer"])


if __name__ == "__main__":
    main()
