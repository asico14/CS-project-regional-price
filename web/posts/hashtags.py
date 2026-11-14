"""Hashtags for channel posts.

Every post ends with a line of hashtags built from its rubric, its
city and optional extra words, in the language of the post, e.g.
"#aksiya #Qoqon #shakar".
"""

import re

RUBRIC_TAGS = {
    "uz": {
        "promotion": "aksiya",
        "price": "narxlar",
        "comparison": "taqqoslash",
        "review": "sharh",
        "lifehack": "foydali_maslahat",
        "store_news": "dokon_yangiliklari",
    },
    "ru": {
        "promotion": "акции",
        "price": "цены",
        "comparison": "сравнение",
        "review": "обзор",
        "lifehack": "лайфхак",
        "store_news": "новости_магазинов",
    },
}

# Uzbek Latin is written with apostrophe-like letters (o', g', tutuq
# belgisi). Telegram ends a hashtag at such a character, so they are
# removed: "Qo'qon" -> "Qoqon".
APOSTROPHES = "'`ʻʼ‘’"
MAX_HASHTAGS = 6


def make_hashtag(text):
    """Turn free text into one Telegram hashtag, or "" if nothing is left.

    Telegram hashtags may contain only letters, digits and underscores,
    and a tag made only of digits is not recognised.
    """
    cleaned = "".join(char for char in str(text) if char not in APOSTROPHES)
    cleaned = re.sub(r"[\s\-–—/]+", "_", cleaned.strip())
    cleaned = re.sub(r"[^\w]", "", cleaned)  # \w is Unicode-aware: keeps Cyrillic
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or cleaned.replace("_", "").isdigit():
        return ""
    return "#" + cleaned


def build_hashtags(rubric, language="uz", city=None, extra=()):
    """Return the list of hashtags for a post, without duplicates.

    Order: rubric, city, then extra words. Duplicates are compared
    without regard to case, and at most MAX_HASHTAGS are returned.
    """
    candidates = []
    rubric_tag = RUBRIC_TAGS.get(language, RUBRIC_TAGS["uz"]).get(rubric)
    if rubric_tag:
        candidates.append(rubric_tag)
    if city:
        candidates.append(getattr(city, "name", city))
    candidates.extend(extra)

    hashtags = []
    seen = set()
    for candidate in candidates:
        hashtag = make_hashtag(candidate)
        if hashtag and hashtag.lower() not in seen:
            seen.add(hashtag.lower())
            hashtags.append(hashtag)
    return hashtags[:MAX_HASHTAGS]


def hashtags_for_post(post):
    return build_hashtags(post.rubric, post.language, post.city)
