"""The publishing loop: every few seconds, publish the posts that are due.

``run_once`` is one pass and is what the tests exercise; ``run_forever``
repeats it until the bot stops. Publishing itself is passed in as an async
function ``publish(post) -> message_id`` so the loop can be tested without
Telegram.
"""

import asyncio
import logging
from datetime import timedelta

import db

logger = logging.getLogger("worker.scheduler")


class PublishFailed(Exception):
    """Raised by ``publish`` with a message meant for the editors."""


class RetryLater(Exception):
    """Raised by ``publish`` when Telegram certainly did NOT send the post
    (e.g. flood control) and it is safe to try again after ``seconds``."""

    def __init__(self, seconds, message="Telegram asked to retry later"):
        super().__init__(message)
        self.seconds = seconds


async def run_once(
    conn, publish, now=None, batch=10, stale_after=timedelta(minutes=10)
):
    """Publish every due post once. Returns a summary dict for logging."""
    now = now or db.utcnow()
    summary = {"stale": db.fail_stale(conn, now, stale_after), "published": 0,
               "failed": 0, "retry": 0, "skipped": 0}
    for post_id in db.due_post_ids(conn, now, batch):
        if not db.claim(conn, post_id, now):
            summary["skipped"] += 1  # another worker got it first
            continue
        post = db.load_post(conn, post_id)
        try:
            message_id = await publish(post)
        except RetryLater as error:
            db.reschedule(conn, post_id, now + timedelta(seconds=error.seconds),
                          error, db.utcnow())
            summary["retry"] += 1
            logger.warning(
                "Post %s: %s, retrying in %ss", post_id, error, error.seconds
            )
        except PublishFailed as error:
            db.mark_failed(conn, post_id, str(error), db.utcnow())
            summary["failed"] += 1
            logger.warning("Post %s failed: %s", post_id, error)
        except Exception as error:  # noqa: BLE001 - any failure ends this attempt
            db.mark_failed(conn, post_id, f"{type(error).__name__}: {error}",
                           db.utcnow())
            summary["failed"] += 1
            logger.exception("Post %s failed", post_id)
        else:
            db.mark_published(conn, post_id, message_id, db.utcnow())
            summary["published"] += 1
            logger.info("Post %s published as message %s", post_id, message_id)
    return summary


async def run_forever(conn, publish, interval=30):
    logger.info("Scheduler started, checking for due posts every %ss", interval)
    while True:
        try:
            summary = await run_once(conn, publish)
            if any(summary.values()):
                logger.info("Scheduler pass: %s", summary)
        except Exception:  # noqa: BLE001 - keep the loop alive (e.g. DB locked)
            logger.exception("Scheduler pass crashed; trying again next time")
        await asyncio.sleep(interval)
