"""Turning a Post into the Telegram message the worker sends.

build_message() decides everything that can be decided without
talking to Telegram: text or photo, the HTML of the message, and
whether the post fits Telegram's limits. The worker only has to send
the result.
"""

import html
import os
from dataclasses import dataclass

from .formatting import CAPTION_LIMIT, TEXT_LIMIT, compose_text, telegram_length
from .hashtags import hashtags_for_post


class PublishError(Exception):
    """The post cannot be published as it is. It becomes "failed" and
    the message is shown to staff, so it should say what to fix."""


class RetryLater(Exception):
    """Telegram did not accept the message right now (flood control).
    Nothing was sent, so the post goes back to "scheduled"."""


@dataclass
class Message:
    kind: str  # "text" or "photo"
    html: str
    photo_path: str = ""


def escape(text):
    """Escape text for Telegram's HTML parse mode.

    Telegram needs only <, > and & escaped. Without this, a title like
    "Narx < 10 000" would be read as a broken tag and the post refused,
    and text typed by staff could inject its own formatting.
    """
    return html.escape(text, quote=False)


def build_html(post):
    """Bold title, text and hashtag line, separated by empty lines."""
    parts = []
    if post.title.strip():
        parts.append(f"<b>{escape(post.title.strip())}</b>")
    if post.text.strip():
        parts.append(escape(post.text.strip()))
    hashtags = hashtags_for_post(post)
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n\n".join(parts)


def build_message(post):
    """Return the Message to send, or raise PublishError."""
    plain = compose_text(post.title, post.text, hashtags_for_post(post))
    if not (post.title.strip() or post.text.strip()):
        raise PublishError("The post is empty.")
    # Telegram counts the text after formatting is applied, so the
    # limit is checked on the plain text, not on the HTML.
    length = telegram_length(plain)

    if post.photo:
        if length > CAPTION_LIMIT:
            raise PublishError(
                f"The post is {length} characters long; Telegram allows "
                f"{CAPTION_LIMIT} for a post with a photo. Shorten the text "
                "or remove the photo."
            )
        if not os.path.exists(post.photo.path):
            raise PublishError("The photo file is missing. Upload the photo again.")
        return Message(kind="photo", html=build_html(post), photo_path=post.photo.path)

    if length > TEXT_LIMIT:
        raise PublishError(
            f"The post is {length} characters long; Telegram allows {TEXT_LIMIT}. "
            "Shorten the text."
        )
    return Message(kind="text", html=build_html(post))
