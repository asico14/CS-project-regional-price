"""A throw-away database with the posts_post columns the worker uses.

The real table is created by Django's migrations; this copy only has the
columns in db.POST_COLUMNS (web/posts/tests_worker_schema.py checks that
the Django model still provides all of them).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402

SCHEMA = """
CREATE TABLE posts_post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    hashtags VARCHAR(300) NOT NULL DEFAULT '',
    image VARCHAR(100) NOT NULL DEFAULT '',
    language VARCHAR(2) NOT NULL DEFAULT 'uz',
    status VARCHAR(12) NOT NULL DEFAULT 'draft',
    scheduled_at DATETIME NULL,
    published_at DATETIME NULL,
    telegram_message_id BIGINT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    locked_at DATETIME NULL,
    last_error TEXT NOT NULL DEFAULT '',
    updated_at DATETIME NOT NULL DEFAULT '',
    comments_enabled BOOL NOT NULL DEFAULT 1
);
"""

NOW = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)


def make_db(path=":memory:"):
    conn = db.connect(path)
    conn.executescript(SCHEMA)
    return conn


def add_post(conn, status="scheduled", minutes=-1, **extra):
    """Insert a post scheduled ``minutes`` from NOW (negative = in the past)."""
    values = {
        "body": "Arzon sut",
        "status": status,
        "scheduled_at": db.to_db(NOW + timedelta(minutes=minutes)),
    }
    values.update(extra)
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cursor = conn.execute(
        f"INSERT INTO posts_post ({columns}) VALUES ({marks})", list(values.values())
    )
    return cursor.lastrowid


def get(conn, post_id):
    return db.load_post(conn, post_id)
