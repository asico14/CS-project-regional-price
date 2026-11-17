"""Database access for the worker (plain sqlite3, no Django).

The worker shares the SQLite file with the web service. The schema is
owned by Django (``web/posts/models.py``); the worker only reads posts
and updates their publishing fields.

How a double publish is prevented
---------------------------------
1. **Atomic claim.** A due post is claimed with a single
   ``UPDATE ... SET status='publishing' WHERE id=? AND status='scheduled'``.
   SQLite runs one write at a time, so if two workers (or two loop runs)
   race for the same post, only one UPDATE changes a row; the other sees
   ``rowcount == 0`` and skips the post.
2. **No automatic retry after an unknown outcome.** Once a post is
   ``publishing`` the worker never puts it back to ``scheduled`` unless
   Telegram said for sure that nothing was sent (flood control). If the
   worker crashes while publishing, the post stays ``publishing``; after
   ``stale_after`` it is marked ``failed`` with a note to check the
   channel, and an editor decides whether to reschedule it.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

TABLE = "posts_post"

# Columns of posts_post that the worker reads or writes. A test in the
# web project checks that the Django model still has all of them.
POST_COLUMNS = (
    "id", "title", "body", "hashtags", "image", "language", "status",
    "scheduled_at", "published_at", "telegram_message_id", "attempts",
    "locked_at", "last_error", "updated_at", "comments_enabled",
)

SCHEDULED = "scheduled"
PUBLISHING = "publishing"
PUBLISHED = "published"
FAILED = "failed"


def connect(path):
    """Open the shared database; wait up to 30 s if the web app is writing."""
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def utcnow():
    return datetime.now(timezone.utc)


def to_db(moment):
    """Format a datetime the way Django stores it in SQLite (naive UTC)."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def due_post_ids(conn, now, limit=10):
    """Scheduled posts whose time has come, oldest first."""
    rows = conn.execute(
        f"SELECT id FROM {TABLE} WHERE status = ? AND scheduled_at <= ? "
        "ORDER BY scheduled_at, id LIMIT ?",
        (SCHEDULED, to_db(now), limit),
    ).fetchall()
    return [row["id"] for row in rows]


def claim(conn, post_id, now):
    """Move one post from scheduled to publishing. True if we got it."""
    cursor = conn.execute(
        f"UPDATE {TABLE} SET status = ?, locked_at = ?, attempts = attempts + 1, "
        "updated_at = ? WHERE id = ? AND status = ?",
        (PUBLISHING, to_db(now), to_db(now), post_id, SCHEDULED),
    )
    return cursor.rowcount == 1


def load_post(conn, post_id):
    row = conn.execute(
        f"SELECT {', '.join(POST_COLUMNS)} FROM {TABLE} WHERE id = ?", (post_id,)
    ).fetchone()
    return dict(row) if row else None


def mark_published(conn, post_id, message_id, now):
    conn.execute(
        f"UPDATE {TABLE} SET status = ?, published_at = ?, telegram_message_id = ?, "
        "locked_at = NULL, last_error = '', updated_at = ? "
        "WHERE id = ? AND status = ?",
        (PUBLISHED, to_db(now), message_id, to_db(now), post_id, PUBLISHING),
    )


def mark_failed(conn, post_id, error, now):
    conn.execute(
        f"UPDATE {TABLE} SET status = ?, locked_at = NULL, last_error = ?, "
        "updated_at = ? WHERE id = ? AND status = ?",
        (FAILED, str(error)[:1000], to_db(now), post_id, PUBLISHING),
    )


def reschedule(conn, post_id, when, error, now):
    """Give a claimed post back to the queue. Only when nothing was sent."""
    conn.execute(
        f"UPDATE {TABLE} SET status = ?, scheduled_at = ?, locked_at = NULL, "
        "last_error = ?, updated_at = ? WHERE id = ? AND status = ?",
        (SCHEDULED, to_db(when), str(error)[:1000], to_db(now), post_id, PUBLISHING),
    )


def fail_stale(conn, now, stale_after=timedelta(minutes=10)):
    """Posts stuck in publishing (worker crashed) become failed, not retried."""
    cursor = conn.execute(
        f"UPDATE {TABLE} SET status = ?, locked_at = NULL, last_error = ?, "
        "updated_at = ? WHERE status = ? AND locked_at < ?",
        (
            FAILED,
            "The worker stopped while publishing this post. Check the channel "
            "before rescheduling it, it may already be there.",
            to_db(now),
            PUBLISHING,
            to_db(now - stale_after),
        ),
    )
    return cursor.rowcount


def count_by_status(conn):
    rows = conn.execute(f"SELECT status, COUNT(*) AS n FROM {TABLE} GROUP BY status")
    return {row["status"]: row["n"] for row in rows}


def comments_enabled_for_message(conn, message_id):
    """True/False for the post published as channel message ``message_id``,
    or None if no post has that message id (yet)."""
    row = conn.execute(
        f"SELECT comments_enabled FROM {TABLE} WHERE telegram_message_id = ? "
        "AND status = ?",
        (message_id, PUBLISHED),
    ).fetchone()
    return None if row is None else bool(row["comments_enabled"])
