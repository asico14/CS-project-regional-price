"""Post generators: turn prices, promotions and baskets into channel posts.

Every generator returns an *unsaved* draft ``Post``; the editor reviews it
in the post editor before scheduling. The text comes from the templates in
``posts/templates/posts/generators/``, rendered in the post's language.
"""

from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext_noop

from catalog.models import Price
from core.templatetags.formatting import som

from .models import Post


def render_text(template_name, context, language):
    """Render a generator template in ``language`` (uz or ru)."""
    with translation.override(language):
        text = render_to_string(f"posts/generators/{template_name}.txt", context)
    # Templates keep one line per sentence; drop blank lines at the edges.
    return text.strip()


def translate(message, language):
    with translation.override(language):
        return translation.gettext(message)


MAX_PRICE_ROWS = 10

# Titles are translated when the post is generated, in the post language.
PROMOTION_TITLE = gettext_noop("Promotion")
PRICE_TITLE = gettext_noop("Prices")


def _date(day):
    return day.strftime("%d.%m.%Y")


def promotion_post(price, language="uz"):
    """A post about one running promotion (a Price with a regular_price)."""
    if not price.is_promotion:
        raise ValueError("This price is not a running promotion.")
    store = price.store
    body = render_text("promotion", {
        "product": str(price.product),
        "store": store.name,
        "city": store.city.name,
        "price": som(price.price),
        "regular_price": som(price.regular_price),
        "discount": price.discount_percent,
        "promo_until": _date(price.promo_until) if price.promo_until else "",
        "address": store.address,
    }, language)
    return Post(
        rubric=Post.Rubric.PROMOTION,
        language=language,
        city=store.city,
        title=f"{translate(PROMOTION_TITLE, language)}: {store.name}",
        body=body,
    )


def price_post(product, language="uz", city=None):
    """Current prices of one product, cheapest store first."""
    prices = (
        Price.objects.current()
        .filter(product=product, store__is_active=True)
        .select_related("store__city")
    )
    if city is not None:
        prices = prices.filter(store__city=city)
    prices = sorted(prices, key=lambda p: (p.effective_price, p.store.name))
    if not prices:
        raise ValueError("There are no prices for this product yet.")
    cheapest, dearest = prices[0].effective_price, prices[-1].effective_price
    shown = prices[:MAX_PRICE_ROWS]
    body = render_text("price", {
        "product": str(product),
        "city": city.name if city else "",
        "rows": [
            {
                "store": (
                    p.store.name if city else f"{p.store.name} ({p.store.city.name})"
                ),
                "price": som(p.effective_price),
            }
            for p in shown
        ],
        "difference": som(dearest - cheapest) if dearest > cheapest else "",
        "percent": round(100 * (dearest - cheapest) / cheapest),
        "date": _date(max(p.observed_on for p in prices)),
    }, language)
    return Post(
        rubric=Post.Rubric.PRICE,
        language=language,
        city=city,
        title=f"{translate(PRICE_TITLE, language)}: {product.name}",
        body=body,
    )
