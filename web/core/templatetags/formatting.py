"""Template filters for numbers as they are written in Uzbekistan."""

from django import template

register = template.Library()


@register.filter
def som(value):
    """12500 -> "12 500" (thin groups separated by a no-break space)."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return value
    return f"{number:,}".replace(",", " ")
