import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from telegram import Chat, MessageOriginChannel, MessageOriginUser, User

from tests.helpers import add_post, make_db

import comments  # importable because tests.helpers put worker/ on sys.path

CHANNEL = Chat(id=-1001, type=Chat.CHANNEL, title="Regional Price")
DATE = datetime(2026, 11, 18, tzinfo=timezone.utc)


class FakeMessage(SimpleNamespace):
    deleted = False

    async def delete(self):
        self.deleted = True
        return True


def forward(message_id, automatic=True):
    return FakeMessage(
        is_automatic_forward=automatic,
        forward_origin=MessageOriginChannel(date=DATE, chat=CHANNEL,
                                            message_id=message_id),
    )


def handle(conn, message):
    update = SimpleNamespace(effective_message=message)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"db": conn}))
    asyncio.run(comments.on_automatic_forward(update, context))


class ChannelMessageIdTests(unittest.TestCase):
    def test_automatic_forward_from_channel(self):
        self.assertEqual(comments.channel_message_id(forward(77)), 77)

    def test_ordinary_messages_are_ignored(self):
        self.assertIsNone(comments.channel_message_id(forward(77, automatic=False)))
        user = User(id=1, first_name="Ali", is_bot=False)
        message = FakeMessage(is_automatic_forward=True,
                              forward_origin=MessageOriginUser(date=DATE, sender_user=user))
        self.assertIsNone(comments.channel_message_id(message))


class CommentsSwitchTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        add_post(self.conn, status="published", telegram_message_id=10,
                 comments_enabled=0)
        add_post(self.conn, status="published", telegram_message_id=11,
                 comments_enabled=1)

    def test_copy_is_deleted_when_comments_are_off(self):
        message = forward(10)
        handle(self.conn, message)
        self.assertTrue(message.deleted)

    def test_copy_is_kept_when_comments_are_on(self):
        message = forward(11)
        handle(self.conn, message)
        self.assertFalse(message.deleted)

    def test_unknown_channel_message_is_left_alone(self):
        original = comments.LOOKUP_DELAY_SECONDS
        comments.LOOKUP_DELAY_SECONDS = 0
        self.addCleanup(setattr, comments, "LOOKUP_DELAY_SECONDS", original)
        message = forward(999)  # e.g. a post an admin wrote by hand
        handle(self.conn, message)
        self.assertFalse(message.deleted)

    def test_lookup_waits_for_the_scheduler_to_save_the_message_id(self):
        post_id = add_post(self.conn, status="publishing", comments_enabled=0)

        async def scenario():
            lookup = asyncio.create_task(
                comments.comments_allowed(self.conn, 12, attempts=5, delay=0.01)
            )
            await asyncio.sleep(0.015)  # the forward arrived first ...
            self.conn.execute(  # ... then the scheduler records the result
                "UPDATE posts_post SET status='published', telegram_message_id=12 "
                "WHERE id=?", (post_id,),
            )
            return await lookup

        self.assertIs(asyncio.run(scenario()), False)


if __name__ == "__main__":
    unittest.main()
