"""Telegram bot worker for the Regional Price & Deals platform.

Runs as its own Docker Compose service and shares the SQLite database
with the Django web service through the "data" volume. Besides answering
a few commands it runs the scheduler (scheduler.py), which publishes the
posts that editors scheduled in the web app to the channel.
"""

import logging
import os
import sqlite3
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import comments
import db
import publisher
import scheduler

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx logs every request URL, and the URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("worker")

DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/db.sqlite3")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/data/media")
POLL_INTERVAL = int(os.environ.get("SCHEDULER_INTERVAL_SECONDS", "30"))
# Discussion group linked to the channel (numeric id, -100...); optional.
DISCUSSION_GROUP_ID = os.environ.get("TELEGRAM_DISCUSSION_GROUP_ID", "").strip()

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
    lines = [f"Worker is running, {database_status()}."]
    try:
        counts = db.count_by_status(context.application.bot_data["db"])
        lines.append(
            "Posts: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
            if counts else "Posts: none yet."
        )
    except (KeyError, sqlite3.Error):
        pass
    await update.message.reply_text("\n".join(lines))


async def start_scheduler(application: Application) -> None:
    conn = db.connect(DATABASE_PATH)
    application.bot_data["db"] = conn
    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL_ID is not set: posts will not be published.")
        return
    application.create_task(
        scheduler.run_forever(
            conn,
            publisher.make_publisher(application.bot, CHANNEL_ID, MEDIA_ROOT),
            POLL_INTERVAL,
        ),
        name="scheduler",
    )


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather, "
            "put it in the .env file and restart the worker."
        )
        sys.exit(1)

    logger.info("Starting worker, %s", database_status())

    application = Application.builder().token(token).post_init(start_scheduler).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("status", status))
    if DISCUSSION_GROUP_ID:
        application.add_handler(comments.make_handler(int(DISCUSSION_GROUP_ID)))
    else:
        logger.info("TELEGRAM_DISCUSSION_GROUP_ID is not set: comments cannot be "
                    "switched off per post.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
