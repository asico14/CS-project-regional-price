"""How a post becomes the text of one Telegram message."""

# Telegram Bot API limits.
TEXT_LIMIT = 4096  # a text message
CAPTION_LIMIT = 1024  # the caption of a photo


def telegram_length(text):
    """Length of the text the way Telegram counts it.

    Telegram counts UTF-16 code units, so most emoji count as 2
    characters. Python's len() would count them as 1 and let a post
    through that Telegram then refuses.
    """
    return len(text.encode("utf-16-le")) // 2


def limit_for(has_photo):
    return CAPTION_LIMIT if has_photo else TEXT_LIMIT


def compose_text(title, text, hashtags):
    """Plain text of the message: title, body and hashtag line."""
    parts = [title.strip(), text.strip(), " ".join(hashtags)]
    return "\n\n".join(part for part in parts if part)
