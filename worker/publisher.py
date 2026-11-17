"""Turn a post row into a Telegram message and send it to the channel.

Message format (same as web/posts/telegram.py, which the editor preview
uses; keep the two in sync)::

    <b>Title</b>

    Body (HTML-escaped: editors write plain text)

    #Hashtags

* With a photo the message is sent with ``sendPhoto`` and the text becomes
  the caption (max 1024 characters); without one, ``sendMessage`` (max 4096).
  Lengths are counted in UTF-16 code units, after HTML parsing.
* Status transitions after an attempt (applied by scheduler.py):

  ===========================  =====================================
  outcome                      post becomes
  ===========================  =====================================
  sent                         published (+ message id)
  flood control (RetryAfter)   scheduled again, after the wait
  anything else                failed, with the reason in last_error
  ===========================  =====================================

  A timeout is *not* retried: Telegram may have posted the message even
  though we got no answer, and a retry could publish it twice.
"""

import os
from datetime import timedelta
from html import escape

from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from scheduler import PublishFailed, RetryLater

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024


class PublishError(PublishFailed):
    """The post cannot be published as it is; an editor must fix it."""


def compose_html(title, body, hashtags):
    parts = []
    if title and title.strip():
        parts.append(f"<b>{escape(title.strip(), quote=False)}</b>")
    if body and body.strip():
        parts.append(escape(body.strip(), quote=False))
    if hashtags and hashtags.strip():
        parts.append(escape(hashtags.strip(), quote=False))
    return "\n\n".join(parts)


def visible_length(title, body, hashtags):
    """Length after HTML parsing, in UTF-16 code units (Telegram's count)."""
    text = "\n\n".join(
        part.strip() for part in (title, body, hashtags) if part and part.strip()
    )
    return len(text.encode("utf-16-le")) // 2


def photo_path(post, media_root):
    if not post.get("image"):
        return None
    return os.path.join(media_root, post["image"])


def prepare(post, media_root):
    """Validate a post and return (html, photo path or None)."""
    html = compose_html(post["title"], post["body"], post["hashtags"])
    if not html:
        raise PublishError("The post is empty.")
    photo = photo_path(post, media_root)
    if photo and not os.path.isfile(photo):
        raise PublishError(f"Photo file not found: {post['image']}")
    length = visible_length(post["title"], post["body"], post["hashtags"])
    limit = CAPTION_LIMIT if photo else TEXT_LIMIT
    if length > limit:
        kind = "photo caption" if photo else "message"
        raise PublishError(
            f"Text is {length} characters; a Telegram {kind} allows {limit}."
        )
    return html, photo


async def send(bot, chat_id, post, media_root):
    """Send one post; return the Telegram message id.

    Raises RetryLater when it is safe to try again, PublishError otherwise.
    """
    html, photo = prepare(post, media_root)
    try:
        if photo:
            with open(photo, "rb") as file:
                message = await bot.send_photo(
                    chat_id=chat_id, photo=file, caption=html,
                    parse_mode=ParseMode.HTML,
                )
        else:
            message = await bot.send_message(
                chat_id=chat_id, text=html, parse_mode=ParseMode.HTML,
            )
    except RetryAfter as error:
        wait = error.retry_after
        seconds = wait.total_seconds() if isinstance(wait, timedelta) else wait
        raise RetryLater(int(seconds) + 1, f"Flood control: {error}") from error
    except TimedOut as error:
        raise PublishError(
            "Telegram did not answer in time. The post may or may not be in "
            "the channel: check before rescheduling it."
        ) from error
    except Forbidden as error:
        raise PublishError(
            f"The bot may not post to the channel ({error}). "
            "Make it an administrator of the channel."
        ) from error
    except BadRequest as error:
        raise PublishError(f"Telegram rejected the post: {error}") from error
    except NetworkError as error:
        raise PublishError(
            f"Network error ({error}). The post may or may not be in the "
            "channel: check before rescheduling it."
        ) from error
    return message.message_id


def make_publisher(bot, chat_id, media_root):
    """The ``publish(post)`` function the scheduler calls."""

    async def publish(post):
        return await send(bot, chat_id, post, media_root)

    return publish
