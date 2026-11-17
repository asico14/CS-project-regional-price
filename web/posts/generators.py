"""Post generators: turn prices, promotions and baskets into channel posts.

Every generator returns an *unsaved* draft ``Post``; the editor reviews it
in the post editor before scheduling. The text comes from the templates in
``posts/templates/posts/generators/``, rendered in the post's language.
"""

from django.template.loader import render_to_string
from django.utils import translation


def render_text(template_name, context, language):
    """Render a generator template in ``language`` (uz or ru)."""
    with translation.override(language):
        text = render_to_string(f"posts/generators/{template_name}.txt", context)
    # Templates keep one line per sentence; drop blank lines at the edges.
    return text.strip()


def translate(message, language):
    with translation.override(language):
        return translation.gettext(message)
