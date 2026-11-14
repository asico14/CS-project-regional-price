"""Telegram bot worker for the Regional Price & Deals platform.

Runs as its own Docker Compose service next to the Django web service.
It uses the same Django code and the same SQLite database (shared
"data" volume), and does two things:

* answers a few bot commands (/start, /ping, /status);
* every POLL_SECONDS looks for scheduled posts whose time has come
  and publishes them to the channel (see web/posts/scheduler.py).
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx logs every request URL, and the URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("worker")

# Make the Django project importable and start Django, so the worker
# can use the models and the scheduler logic of the web service.
WEB_DIR = os.environ.get("WEB_DIR", str(Path(__file__).resolve().parent.parent / "web"))
sys.path.insert(0, WEB_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.db import close_old_connections  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.constants import ParseMode  # noqa: E402
from telegram.error import RetryAfter  # noqa: E402
from telegram.ext import Application, CommandHandler, ContextTypes  # noqa: E402

from posts.models import Post  # noqa: E402
from posts.publishing import RetryLater, build_message  # noqa: E402
from posts.scheduler import run_once  # noqa: E402

POLL_SECONDS = int(os.environ.get("WORKER_POLL_SECONDS", "30"))
SEND_TIMEOUT = 60

CITIES = ["Qo'qon", "Farg'ona", "Andijon", "Namangan", "Marg'ilon"]


def database_status() -> str:
    """Describe whether the database shared with the web service is reachable."""
    close_old_connections()
    try:
        counts = {
            status: Post.objects.filter(status=status).count()
            for status in (Post.Status.SCHEDULED, Post.Status.PUBLISHED, Post.Status.FAILED)
        }
    except Exception as error:  # e.g. the web service has not migrated yet
        return f"database error: {error}"
    finally:
        close_old_connections()
    return "database ok ({scheduled} scheduled, {published} published, {failed} failed posts)".format(
        **counts
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Assalomu alaykum! This is the Regional Price & Deals bot for the "
        "Fergana Valley (" + ", ".join(CITIES) + ").\n"
        "Commands: /ping, /status"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Database calls are blocking, so they run in a separate thread.
    text = await asyncio.to_thread(database_status)
    await update.message.reply_text(f"Worker is running, {text}.")


async def send_to_channel(bot, channel_id, message):
    """Send a built message: a photo with a caption, or a text message."""
    if message.kind == "photo":
        with open(message.photo_path, "rb") as photo:
            return await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=message.html,
                parse_mode=ParseMode.HTML,
            )
    return await bot.send_message(
        chat_id=channel_id, text=message.html, parse_mode=ParseMode.HTML
    )


def publish_due_posts(bot, channel_id, loop) -> int:
    """One scheduler pass. Runs in a worker thread, not in the event loop."""

    def send(post):
        # Raises PublishError if the post cannot be sent as it is.
        message = build_message(post)
        # The bot is asynchronous: hand the call to the event loop and
        # wait here for the answer.
        future = asyncio.run_coroutine_threadsafe(
            send_to_channel(bot, channel_id, message), loop
        )
        try:
            return future.result(timeout=SEND_TIMEOUT).message_id
        except RetryAfter as error:
            # Flood control: Telegram sent nothing and says when to retry.
            raise RetryLater(f"Telegram asks to retry in {error.retry_after} s") from error

    close_old_connections()
    try:
        return run_once(send)
    finally:
        close_old_connections()


async def scheduler_loop(application: Application, channel_id: str) -> None:
    loop = asyncio.get_running_loop()
    logger.info("Scheduler started: checking for due posts every %s s", POLL_SECONDS)
    while True:
        try:
            await asyncio.to_thread(publish_due_posts, application.bot, channel_id, loop)
        except Exception:
            # Never let one bad pass kill the loop; try again next time.
            logger.exception("Scheduler pass failed")
        await asyncio.sleep(POLL_SECONDS)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        logger.error(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID must be set. Get a token "
            "from @BotFather, add the bot to the channel as an administrator, "
            "put both values in the .env file and restart the worker."
        )
        sys.exit(1)

    async def on_start(application: Application) -> None:
        application.bot_data["scheduler"] = asyncio.create_task(
            scheduler_loop(application, channel_id)
        )

    async def on_stop(application: Application) -> None:
        application.bot_data["scheduler"].cancel()

    logger.info("Starting worker, %s", database_status())
    application = (
        Application.builder().token(token).post_init(on_start).post_stop(on_stop).build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("status", status))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
