"""How a post becomes a Telegram message, and Telegram's size limits.

The editor types plain text; we never trust it as HTML. The message is::

    <b>Title</b>            (optional)

    Body text, HTML-escaped

    #Rubric #City #Extra

and is sent with ``parse_mode=HTML``. The worker builds the same message
in ``worker/publisher.py``; keep the two in sync.

Lengths are counted in UTF-16 code units, like Telegram does (an emoji
counts as 2), on the text *after* HTML parsing, i.e. without the tags.
"""

from html import escape

TEXT_LIMIT = 4096  # sendMessage
CAPTION_LIMIT = 1024  # sendPhoto caption


def _parts(title, body, hashtags):
    return [part for part in (title.strip(), body.strip(), hashtags.strip()) if part]


def compose_plain(title, body, hashtags):
    return "\n\n".join(_parts(title, body, hashtags))


def compose_html(title, body, hashtags):
    title, body, hashtags = title.strip(), body.strip(), hashtags.strip()
    parts = []
    if title:
        parts.append(f"<b>{escape(title, quote=False)}</b>")
    if body:
        parts.append(escape(body, quote=False))
    if hashtags:
        parts.append(escape(hashtags, quote=False))
    return "\n\n".join(parts)


def telegram_length(text):
    """Length as Telegram counts it (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


def length_limit(has_image):
    return CAPTION_LIMIT if has_image else TEXT_LIMIT
