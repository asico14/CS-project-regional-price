"""Hashtags for channel posts.

Every post gets up to ``MAX_HASHTAGS`` hashtags, in this order:

1. the rubric tag in the post's language (``#Aksiya`` / ``#Акция``),
2. the city tag, if the post is about one city (``#Qoqon``),
3. the editor's extra tags.

Telegram only treats letters, digits and ``_`` as part of a hashtag, so
``Qo'qon`` would be cut to ``#Qo``. ``to_hashtag`` therefore drops the
apostrophes used in Uzbek Latin (' ‘ ’ ʻ ʼ `) and joins multiword names in
CamelCase: "Marg'ilon dehqon bozori" -> ``#MargilonDehqonBozori``.
"""

import re

MAX_HASHTAGS = 5
MAX_TAG_LENGTH = 40

APOSTROPHES = "'‘’ʻʼ`´"
_APOSTROPHE_RE = re.compile(f"[{APOSTROPHES}]")
# Anything that is not a letter, digit or underscore separates words.
_SEPARATOR_RE = re.compile(r"[\W_]+", re.UNICODE)

RUBRIC_TAGS = {
    "uz": {
        "promotion": "Aksiya",
        "price": "Narxlar",
        "comparison": "SavatSolishtirish",
        "review": "Sharh",
        "lifehack": "Layfxak",
        "store_news": "DokonYangiliklari",
    },
    "ru": {
        "promotion": "Акция",
        "price": "Цены",
        "comparison": "СравнениеКорзины",
        "review": "Обзор",
        "lifehack": "Лайфхак",
        "store_news": "НовостиМагазинов",
    },
}


def to_hashtag(text):
    """Turn free text into a valid hashtag, or return None if impossible."""
    text = _APOSTROPHE_RE.sub("", text or "").lstrip("#")
    words = [w for w in _SEPARATOR_RE.split(text) if w]
    tag = "".join(w[0].upper() + w[1:] for w in words)[:MAX_TAG_LENGTH]
    # A hashtag needs at least one letter: "#2026" is not linked by Telegram.
    if not any(ch.isalpha() for ch in tag):
        return None
    return "#" + tag


def split_extra_tags(text):
    """Editor input: tags separated by commas or new lines (or '#')."""
    return [part for part in re.split(r"[,\n#]+", text or "") if part.strip()]


def build_hashtags(rubric, language="uz", city_name="", extra=""):
    """The ordered, de-duplicated list of hashtags for a post."""
    candidates = [RUBRIC_TAGS.get(language, RUBRIC_TAGS["uz"]).get(rubric, "")]
    candidates.append(city_name or "")
    candidates.extend(split_extra_tags(extra))
    tags, seen = [], set()
    for candidate in candidates:
        tag = to_hashtag(candidate)
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags[:MAX_HASHTAGS]
