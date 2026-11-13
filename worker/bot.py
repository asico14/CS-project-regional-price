"""Telegram bot worker for the Regional Price & Deals platform.

Runs as its own Docker Compose service and shares the SQLite database
with the Django web service through the "data" volume.
"""

import logging
import os
import sqlite3
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx logs every request URL, and the URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("worker")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/db.sqlite3")

CITIES = ["Qo'qon", "Farg'ona", "Andijon", "Namangan", "Marg'ilon"]


def database_status() -> str:
    """Describe whether the database shared with the web service is reachable."""
    if not os.path.exists(DATABASE_PATH):
        return "database file not found (has the web service run migrations?)"
    try:
        # Open read-only: the worker must not create or change the schema.
        with sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True) as conn:
            (tables,) = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()
    except sqlite3.Error as error:
        return f"database error: {error}"
    return f"database ok ({tables} tables)"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Assalomu alaykum! This is the Regional Price & Deals bot for the "
        "Fergana Valley (" + ", ".join(CITIES) + ").\n"
        "Commands: /ping, /status"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Worker is running, {database_status()}.")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather, "
            "put it in the .env file and restart the worker."
        )
        sys.exit(1)

    logger.info("Starting worker, %s", database_status())

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("status", status))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
