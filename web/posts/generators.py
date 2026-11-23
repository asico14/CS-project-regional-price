"""Post generators: turn prices, promotions and baskets into channel posts.

Every generator returns an *unsaved* draft ``Post``; the editor reviews it
in the post editor before scheduling. The text comes from the templates in
``posts/templates/posts/generators/``, rendered in the post's language.
"""

from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext_noop

from baskets.services import compare_basket
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


MAX_RANKING_ROWS = 5
MEDALS = ["🥇", "🥈", "🥉"]
COMPARISON_TITLE = gettext_noop("Where is the basket cheapest?")
NEW_STORE_TITLE = gettext_noop("New store")


def comparison_post(basket, language="uz", city=None):
    """Store ranking for a basket (see baskets.services.compare_basket)."""
    comparison = compare_basket(basket, city=city)
    results = comparison.results
    if not results:
        raise ValueError("No store has prices for the products of this basket.")
    shown = results[:MAX_RANKING_ROWS]
    best, worst = results[0], results[-1]
    rows = []
    for position, result in enumerate(shown):
        store = result.store
        medal = MEDALS[position] if position < len(MEDALS) else f"{position + 1}."
        rows.append({
            "medal": medal,
            "store": store.name if city else f"{store.name} ({store.city.name})",
            "total": som(result.estimated_total),
            "estimated": not result.is_complete,
        })
    contents = ", ".join(
        f"{item.quantity.normalize():f} × {item.product.name}"
        for item in basket.items.select_related("product")
    )
    savings = worst.estimated_total - best.estimated_total
    body = render_text("comparison", {
        "basket": basket.name,
        "contents": contents,
        "rows": rows,
        "best": best.store.name,
        "worst": worst.store.name,
        "savings": som(savings) if savings > 0 and len(results) > 1 else "",
        "has_estimates": any(row["estimated"] for row in rows),
    }, language)
    return Post(
        rubric=Post.Rubric.COMPARISON,
        language=language,
        city=city,
        title=translate(COMPARISON_TITLE, language),
        body=body,
    )


def new_store_post(store, language="uz"):
    """Announce a store whose prices the channel now tracks."""
    product_count = (
        Price.objects.filter(store=store).values("product").distinct().count()
    )
    body = render_text("new_store", {
        "store": store.name,
        "city": store.city.name,
        "district": store.district.name if store.district_id else "",
        "address": store.address,
        "product_count": product_count,
    }, language)
    return Post(
        rubric=Post.Rubric.STORE_NEWS,
        language=language,
        city=store.city,
        title=f"{translate(NEW_STORE_TITLE, language)}: {store.name}",
        body=body,
    )
