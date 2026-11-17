"""Per-post comments through the channel's linked discussion group.

How Telegram channel comments work: when a channel has a linked
discussion group, Telegram copies ("automatically forwards") every new
channel post into that group, and the comments under the post are the
replies to that copy. If the copy is deleted, the post has no comment
thread: the "Leave a comment" button disappears.

So to switch comments *off* for one post, the bot (an administrator of
the discussion group with the "delete messages" right) watches the group
for automatic forwards, looks up which post the forward belongs to and
deletes the copy if the editor unticked "comments" for that post.

Telegram may deliver the forward a moment before the scheduler has saved
the message id of the post it just sent, so an unknown message id is
looked up again a few times before giving up.
"""

import asyncio
import logging

from telegram import MessageOriginChannel, Update
from telegram.ext import ContextTypes, MessageHandler, filters

import db

logger = logging.getLogger("worker.comments")

LOOKUP_ATTEMPTS = 5
LOOKUP_DELAY_SECONDS = 2


def channel_message_id(message):
    """The id of the channel post that ``message`` is the group copy of."""
    if not message.is_automatic_forward:
        return None
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel):
        return origin.message_id
    return None


async def comments_allowed(conn, message_id, attempts=None, delay=None):
    """True/False from the post, None if it is not one of our posts."""
    attempts = LOOKUP_ATTEMPTS if attempts is None else attempts
    delay = LOOKUP_DELAY_SECONDS if delay is None else delay
    for attempt in range(attempts):
        allowed = db.comments_enabled_for_message(conn, message_id)
        if allowed is not None:
            return allowed
        if attempt < attempts - 1:
            await asyncio.sleep(delay)
    return None


async def on_automatic_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    message_id = channel_message_id(message)
    if message_id is None:
        return
    conn = context.application.bot_data["db"]
    allowed = await comments_allowed(conn, message_id)
    if allowed is False:
        await message.delete()
        logger.info("Comments switched off for channel message %s", message_id)
    elif allowed is None:
        logger.info("Channel message %s is not a scheduled post; left alone",
                    message_id)


def make_handler(discussion_group_id):
    """Handler for automatic forwards in the linked discussion group."""
    return MessageHandler(
        filters.Chat(chat_id=discussion_group_id) & filters.IS_AUTOMATIC_FORWARD,
        on_automatic_forward,
    )
