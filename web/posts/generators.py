"""Generated posts: text built from the data instead of typed by hand.

Each kind of post has a template in templates/posts/generators/.
The templates use Django's translation tags, so one template gives
the Uzbek and the Russian version (see locale/*/LC_MESSAGES/django.po).
The first line of a rendered template is the post title, the rest is
the post text.
"""

import re

from django.template.loader import render_to_string
from django.utils import translation


def format_price(amount):
    """12500 -> "12 500" (the same in both languages)."""
    return f"{round(amount):,}".replace(",", " ")


def format_date(day):
    return day.strftime("%d.%m.%Y")


def render_generator(name, language, context):
    """Render templates/posts/generators/<name>.txt in the given language.

    Returns (title, text).
    """
    with translation.override(language):
        rendered = render_to_string(f"posts/generators/{name}.txt", context)
    lines = [line.rstrip() for line in rendered.strip().splitlines()]
    title = lines[0]
    text = "\n".join(lines[1:]).strip()
    # Template tags leave empty lines behind; keep at most one in a row.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text
