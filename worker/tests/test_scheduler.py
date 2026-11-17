import asyncio
import os
import tempfile
import unittest
from datetime import timedelta

from tests.helpers import NOW, add_post, db, get, make_db

import scheduler  # importable because tests.helpers put worker/ on sys.path


def run(coro):
    return asyncio.run(coro)


class Recorder:
    """A fake publish(): records posts and returns message ids 100, 101..."""

    def __init__(self, error=None):
        self.posts = []
        self.error = error

    async def __call__(self, post):
        self.posts.append(post["id"])
        if self.error:
            raise self.error
        return 99 + len(self.posts)


class DueSelectionTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()

    def test_only_scheduled_posts_whose_time_has_come(self):
        due_late = add_post(self.conn, minutes=-30)
        due_now = add_post(self.conn, minutes=0)
        add_post(self.conn, minutes=+5)  # future
        add_post(self.conn, status="draft", minutes=-60)
        add_post(self.conn, status="published", minutes=-60)
        add_post(self.conn, status="failed", minutes=-60)
        self.assertEqual(db.due_post_ids(self.conn, NOW), [due_late, due_now])

    def test_django_format_without_microseconds_compares_correctly(self):
        # Django omits ".000000" when the microseconds are zero.
        post = add_post(self.conn, scheduled_at="2026-11-18 09:00:00")
        self.assertEqual(db.due_post_ids(self.conn, NOW), [post])
        self.assertEqual(db.due_post_ids(self.conn, NOW - timedelta(seconds=1)), [])

    def test_batch_limit(self):
        for _ in range(5):
            add_post(self.conn)
        self.assertEqual(len(db.due_post_ids(self.conn, NOW, limit=3)), 3)


class RunOnceTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()

    def test_publishes_due_posts(self):
        first, second = add_post(self.conn, minutes=-2), add_post(self.conn)
        future = add_post(self.conn, minutes=10)
        publish = Recorder()
        summary = run(scheduler.run_once(self.conn, publish, now=NOW))
        self.assertEqual(publish.posts, [first, second])
        self.assertEqual(summary["published"], 2)
        post = get(self.conn, first)
        self.assertEqual(
            (post["status"], post["telegram_message_id"], post["attempts"]),
            ("published", 100, 1),
        )
        self.assertIsNotNone(post["published_at"])
        self.assertIsNone(post["locked_at"])
        self.assertEqual(get(self.conn, future)["status"], "scheduled")

    def test_second_pass_publishes_nothing_again(self):
        add_post(self.conn)
        publish = Recorder()
        run(scheduler.run_once(self.conn, publish, now=NOW))
        run(scheduler.run_once(self.conn, publish, now=NOW + timedelta(minutes=1)))
        self.assertEqual(len(publish.posts), 1)

    def test_error_marks_post_failed(self):
        post_id = add_post(self.conn)
        failing = Recorder(RuntimeError("Chat not found"))
        run(scheduler.run_once(self.conn, failing, now=NOW))
        post = get(self.conn, post_id)
        self.assertEqual(post["status"], "failed")
        self.assertEqual(post["last_error"], "RuntimeError: Chat not found")
        # A failed post is not picked up again by itself.
        publish = Recorder()
        run(scheduler.run_once(self.conn, publish, now=NOW + timedelta(hours=1)))
        self.assertEqual(publish.posts, [])

    def test_retry_later_puts_post_back_in_the_queue(self):
        post_id = add_post(self.conn)
        flood = Recorder(scheduler.RetryLater(30))
        run(scheduler.run_once(self.conn, flood, now=NOW))
        post = get(self.conn, post_id)
        self.assertEqual(post["status"], "scheduled")
        self.assertEqual(post["scheduled_at"], db.to_db(NOW + timedelta(seconds=30)))
        self.assertEqual(db.due_post_ids(self.conn, NOW), [])
        later = NOW + timedelta(seconds=30)
        self.assertEqual(db.due_post_ids(self.conn, later), [post_id])


class NoDoublePublishTests(unittest.TestCase):
    """Several connections to one database file, like two worker processes."""

    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.addCleanup(os.remove, self.path)
        make_db(self.path).close()

    def connection(self):
        conn = db.connect(self.path)
        self.addCleanup(conn.close)
        return conn

    def test_claim_is_atomic_across_connections(self):
        a, b = self.connection(), self.connection()
        post_id = add_post(a)
        self.assertTrue(db.claim(a, post_id, NOW))
        self.assertFalse(db.claim(b, post_id, NOW))  # the second worker loses
        self.assertEqual(get(b, post_id)["attempts"], 1)

    def test_two_concurrent_schedulers_publish_each_post_once(self):
        a, b = self.connection(), self.connection()
        ids = [add_post(a) for _ in range(6)]
        publish = Recorder()

        async def both():
            await asyncio.gather(
                scheduler.run_once(a, publish, now=NOW),
                scheduler.run_once(b, publish, now=NOW),
            )

        run(both())
        self.assertEqual(sorted(publish.posts), ids)

    def test_post_stuck_in_publishing_becomes_failed_not_retried(self):
        conn = self.connection()
        stuck = add_post(conn, status="publishing",
                         locked_at=db.to_db(NOW - timedelta(minutes=11)))
        recent = add_post(conn, status="publishing",
                          locked_at=db.to_db(NOW - timedelta(minutes=2)))
        publish = Recorder()
        summary = run(scheduler.run_once(conn, publish, now=NOW))
        self.assertEqual(summary["stale"], 1)
        self.assertEqual(publish.posts, [])
        self.assertEqual(get(conn, stuck)["status"], "failed")
        self.assertIn("Check the channel", get(conn, stuck)["last_error"])
        self.assertEqual(get(conn, recent)["status"], "publishing")

    def test_late_result_cannot_overwrite_a_changed_post(self):
        conn = self.connection()
        post_id = add_post(conn)
        db.claim(conn, post_id, NOW)
        db.fail_stale(conn, NOW + timedelta(hours=1))  # declared stale meanwhile
        db.mark_published(conn, post_id, 5, NOW)  # only applies to "publishing"
        self.assertEqual(get(conn, post_id)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
