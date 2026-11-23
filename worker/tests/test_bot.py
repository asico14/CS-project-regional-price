import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace

from tests.helpers import add_post, make_db

import bot  # importable because tests.helpers put worker/ on sys.path


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def call(handler, bot_data=None):
    message = FakeMessage()
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(application=SimpleNamespace(bot_data=bot_data or {}))
    asyncio.run(handler(update, context))
    return message.replies


class CommandTests(unittest.TestCase):
    def test_start_lists_cities_and_commands(self):
        (reply,) = call(bot.start)
        self.assertIn("Qo'qon", reply)
        self.assertIn("/status", reply)

    def test_ping(self):
        self.assertEqual(call(bot.ping), ["pong"])

    def test_status_with_post_counts(self):
        conn = make_db()
        add_post(conn, status="scheduled")
        add_post(conn, status="published")
        add_post(conn, status="published")
        (reply,) = call(bot.status, {"db": conn})
        self.assertIn("Worker is running", reply)
        self.assertIn("Posts: 2 published, 1 scheduled", reply)

    def test_status_without_database(self):
        (reply,) = call(bot.status)
        self.assertIn("Worker is running", reply)


class DatabaseStatusTests(unittest.TestCase):
    def test_missing_file(self):
        original = bot.DATABASE_PATH
        self.addCleanup(setattr, bot, "DATABASE_PATH", original)
        bot.DATABASE_PATH = "/nonexistent/db.sqlite3"
        self.assertIn("not found", bot.database_status())

    def test_existing_file(self):
        handle, path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.addCleanup(os.remove, path)
        make_db(path).close()
        original = bot.DATABASE_PATH
        self.addCleanup(setattr, bot, "DATABASE_PATH", original)
        bot.DATABASE_PATH = path
        self.assertIn("database ok", bot.database_status())


class FakeApplication:
    def __init__(self):
        self.bot = object()
        self.bot_data = {}
        self.tasks = []

    def create_task(self, coro, name=None):
        self.tasks.append(name)
        coro.close()  # not run in the test


class StartSchedulerTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(handle)
        self.addCleanup(os.remove, self.path)
        for name in ("DATABASE_PATH", "CHANNEL_ID"):
            self.addCleanup(setattr, bot, name, getattr(bot, name))
        bot.DATABASE_PATH = self.path

    def start(self):
        app = FakeApplication()
        asyncio.run(bot.start_scheduler(app))
        self.addCleanup(app.bot_data["db"].close)
        return app

    def test_without_channel_nothing_is_published(self):
        bot.CHANNEL_ID = ""
        app = self.start()
        self.assertEqual(app.tasks, [])
        self.assertIn("db", app.bot_data)

    def test_with_channel_the_scheduler_starts(self):
        bot.CHANNEL_ID = "@channel"
        self.assertEqual(self.start().tasks, ["scheduler"])

    def test_main_needs_a_token(self):
        original = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        if original is not None:
            self.addCleanup(os.environ.__setitem__, "TELEGRAM_BOT_TOKEN", original)
        with self.assertRaises(SystemExit), self.assertLogs("worker", "ERROR"):
            bot.main()


if __name__ == "__main__":
    unittest.main()
