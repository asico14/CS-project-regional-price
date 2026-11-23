import asyncio
import os
import tempfile
import unittest
from datetime import timedelta
from types import SimpleNamespace

from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from tests.helpers import NOW, add_post, get, make_db

import publisher  # importable because tests.helpers put worker/ on sys.path
import scheduler


class FakeBot:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def _answer(self, method, **kwargs):
        if "photo" in kwargs:
            kwargs["photo"] = kwargs["photo"].read()
        self.calls.append((method, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(message_id=42)

    async def send_message(self, **kwargs):
        return await self._answer("send_message", **kwargs)

    async def send_photo(self, **kwargs):
        return await self._answer("send_photo", **kwargs)


def post(**extra):
    data = {"id": 1, "title": "", "body": "Arzon sut", "hashtags": "#Aksiya",
            "image": ""}
    data.update(extra)
    return data


def send(bot, row, media_root="/nonexistent"):
    return asyncio.run(publisher.send(bot, "@channel", row, media_root))


class ComposeTests(unittest.TestCase):
    def test_title_bold_and_text_escaped(self):
        html = publisher.compose_html("Sut <arzon>", "1 < 2 & \"ok\"", "#Aksiya")
        self.assertEqual(html, '<b>Sut &lt;arzon&gt;</b>\n\n1 &lt; 2 &amp; "ok"\n\n#Aksiya')

    def test_empty_parts_are_skipped(self):
        self.assertEqual(publisher.compose_html("", "  Sut ", ""), "Sut")

    def test_length_ignores_markup_and_counts_utf16(self):
        self.assertEqual(publisher.visible_length("A&B", "🔥", ""), len("A&B\n\n") + 2)


class SendTests(unittest.TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.media, "posts"))
        self.photo = "posts/p.jpg"
        with open(os.path.join(self.media, self.photo), "wb") as file:
            file.write(b"jpeg-bytes")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.media)

    def test_text_post_uses_send_message_with_html(self):
        bot = FakeBot()
        self.assertEqual(send(bot, post(title="Aksiya")), 42)
        ((method, kwargs),) = bot.calls
        self.assertEqual(method, "send_message")
        self.assertEqual(kwargs["text"], "<b>Aksiya</b>\n\nArzon sut\n\n#Aksiya")
        self.assertEqual(kwargs["parse_mode"], ParseMode.HTML)
        self.assertEqual(kwargs["chat_id"], "@channel")

    def test_photo_post_uses_send_photo_with_caption(self):
        bot = FakeBot()
        send(bot, post(image=self.photo), self.media)
        ((method, kwargs),) = bot.calls
        self.assertEqual(method, "send_photo")
        self.assertEqual(kwargs["photo"], b"jpeg-bytes")
        self.assertEqual(kwargs["caption"], "Arzon sut\n\n#Aksiya")

    def test_limits(self):
        bot = FakeBot()
        send(bot, post(body="x" * 4087, hashtags="#Aksiya"))  # exactly 4096
        with self.assertRaisesRegex(publisher.PublishError, "allows 4096"):
            send(bot, post(body="x" * 4088))
        with self.assertRaisesRegex(publisher.PublishError, "caption allows 1024"):
            send(bot, post(body="x" * 1100, image=self.photo), self.media)
        # Escaping makes the HTML longer but not the visible text.
        send(bot, post(body="&" * 4000, hashtags=""))
        self.assertEqual(len(bot.calls), 2)

    def test_missing_photo_and_empty_post(self):
        with self.assertRaisesRegex(publisher.PublishError, "not found"):
            send(FakeBot(), post(image="posts/gone.jpg"), self.media)
        with self.assertRaisesRegex(publisher.PublishError, "empty"):
            send(FakeBot(), post(body=" ", hashtags=""))

    def test_flood_control_means_retry_later(self):
        for wait in (12, timedelta(seconds=12)):
            with self.assertRaises(scheduler.RetryLater) as caught:
                send(FakeBot(RetryAfter(wait)), post())
            self.assertEqual(caught.exception.seconds, 13)

    def test_other_errors_are_publish_errors(self):
        cases = [
            (TimedOut(), "may or may not"),
            (NetworkError("reset"), "may or may not"),
            (Forbidden("bot is not a member"), "administrator"),
            (BadRequest("Can't parse entities"), "rejected"),
        ]
        for error, text in cases:
            with self.subTest(error=error), self.assertRaisesRegex(
                publisher.PublishError, text
            ):
                send(FakeBot(error), post())


class StatusTransitionTests(unittest.TestCase):
    """The scheduler applies the publisher's outcome to the post row."""

    def run_with(self, bot):
        conn = make_db()
        post_id = add_post(conn, title="T")
        publish = publisher.make_publisher(bot, "@channel", "/nonexistent")
        asyncio.run(scheduler.run_once(conn, publish, now=NOW))
        return get(conn, post_id)

    def test_sent(self):
        row = self.run_with(FakeBot())
        self.assertEqual((row["status"], row["telegram_message_id"]), ("published", 42))

    def test_flood_control(self):
        row = self.run_with(FakeBot(RetryAfter(5)))
        self.assertEqual(row["status"], "scheduled")
        self.assertIn("Flood control", row["last_error"])

    def test_timeout_is_not_retried(self):
        row = self.run_with(FakeBot(TimedOut()))
        self.assertEqual(row["status"], "failed")
        self.assertTrue(row["last_error"].startswith("Telegram did not answer"))


if __name__ == "__main__":
    unittest.main()
