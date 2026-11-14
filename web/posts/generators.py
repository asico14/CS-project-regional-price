"""Generated posts: text built from the data instead of typed by hand.

Each kind of post has a template in templates/posts/generators/.
The templates use Django's translation tags, so one template gives
the Uzbek and the Russian version (see locale/*/LC_MESSAGES/django.po).
The first line of a rendered template is the post title, the rest is
the post text.
"""

import re

from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone, translation

from baskets.services import compare_basket
from catalog.models import Price
from catalog.services import current_prices

from .formatting import TEXT_LIMIT, compose_text, telegram_length
from .hashtags import build_hashtags
from .models import Post

MAX_ITEMS = 10


class NothingToPost(Exception):
    """There is no data to build this post from (e.g. no promotions)."""


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


def store_label(store, city):
    """Store name; with the city when the post covers the whole valley."""
    return store.name if city is not None else f"{store.name} ({store.city.name})"


def build_draft(rubric, name, language, city, context, items, user=None):
    """Render a generator template into an unsaved draft Post.

    If the message would be longer than Telegram allows, items are
    dropped from the end of the list until it fits.
    """
    shown = len(items)
    while True:
        title, text = render_generator(
            name,
            language,
            {**context, "items": items[:shown], "more": len(items) - shown},
        )
        hashtags = build_hashtags(rubric, language, city)
        fits = telegram_length(compose_text(title, text, hashtags)) <= TEXT_LIMIT
        if fits or shown <= 1:
            break
        shown -= 1
    return Post(
        rubric=rubric,
        language=language,
        city=city,
        title=title[:200],
        text=text,
        status=Post.Status.DRAFT,
        created_by=user,
    )


def generate_promotion_post(city=None, language="uz", user=None):
    """Draft post listing the promotions that are running now."""
    today = timezone.localdate()
    promotions = (
        Price.objects.current()
        .filter(is_promo=True, store__is_active=True, product__is_active=True)
        .filter(Q(promo_ends__isnull=True) | Q(promo_ends__gte=today))
        .select_related("product", "store", "store__city")
    )
    if city is not None:
        promotions = promotions.filter(store__city=city)

    items = []
    for promo in promotions:
        # The regular price right before the promotion, to show the saving.
        before = (
            Price.objects.filter(
                product=promo.product,
                store=promo.store,
                is_promo=False,
                recorded_at__lte=promo.recorded_at,
            )
            .order_by("-recorded_at", "-id")
            .first()
        )
        percent = 0
        if before and before.amount > promo.amount:
            percent = round((1 - promo.amount / before.amount) * 100)
        items.append(
            {
                "product": str(promo.product),
                "price": format_price(promo.amount),
                "old_price": format_price(before.amount) if percent else None,
                "percent": percent,
                "store": store_label(promo.store, city),
                "ends": format_date(promo.promo_ends) if promo.promo_ends else None,
            }
        )
    if not items:
        raise NothingToPost("There are no running promotions.")

    # Biggest discounts first; only the best ones go into the post.
    items.sort(key=lambda item: (-item["percent"], item["product"], item["store"]))
    context = {"city": city.name if city else None}
    draft = build_draft(
        Post.Rubric.PROMOTION, "promotion", language, city, context, items[:MAX_ITEMS], user
    )
    if len(items) > MAX_ITEMS:
        # "…and N more" must count everything that was left out.
        shown = draft.text.count("🔥")
        title, text = render_generator(
            "promotion",
            language,
            {**context, "items": items[:shown], "more": len(items) - shown},
        )
        draft.title, draft.text = title[:200], text
    return draft


def generate_price_post(product, city=None, language="uz", user=None):
    """Draft post comparing the current price of one product between stores."""
    rows = [row for row in current_prices(product, city=city) if not row["expired"]]
    if not rows:
        raise NothingToPost("There are no current prices for this product.")
    items = [
        {
            "store": store_label(row["price"].store, city),
            "price": format_price(row["price"].amount),
            "cheapest": row["cheapest"],
            "promo": row["price"].is_promo,
        }
        for row in rows[:MAX_ITEMS]
    ]
    difference = rows[-1]["price"].amount - rows[0]["price"].amount
    context = {
        "product": str(product),
        "city": city.name if city else None,
        "difference": format_price(difference) if difference > 0 else None,
        "date": format_date(timezone.localdate()),
    }
    return build_draft(Post.Rubric.PRICE, "price", language, city, context, items, user)


def format_quantity(quantity):
    """Decimal("2.000") -> "2", Decimal("0.500") -> "0.5"."""
    return f"{quantity.normalize():f}"


def generate_basket_post(basket, city=None, language="uz", user=None):
    """Draft post ranking the stores by the total price of a basket.

    Only stores that have every product of the basket are ranked; the
    post says how many stores were left out for that reason.
    """
    results = compare_basket(basket, city=city)
    ranked = [result for result in results if result.complete]
    if not ranked:
        raise NothingToPost("No store has prices for every product of this basket.")
    items = [
        {
            "place": result.rank,
            "store": store_label(result.store, city),
            "total": format_price(result.total),
            "extra": format_price(result.extra) if result.extra > 0 else None,
        }
        for result in ranked[:MAX_ITEMS]
    ]
    saving = ranked[-1].total - ranked[0].total
    contents = ", ".join(
        f"{format_quantity(item.quantity)} × {item.product.name}"
        for item in basket.items.select_related("product")
    )
    context = {
        "basket": basket.name,
        "city": city.name if city else None,
        "contents": contents,
        "saving": format_price(saving) if saving > 0 else None,
        "skipped": len(results) - len(ranked),
        "date": format_date(timezone.localdate()),
    }
    return build_draft(
        Post.Rubric.COMPARISON, "basket", language, city, context, items, user
    )


def generate_store_post(store, language="uz", user=None):
    """Draft post announcing a store whose prices are now tracked."""
    today = timezone.localdate()
    city_prices = (
        Price.objects.current()
        .filter(store__city=store.city, store__is_active=True)
        .exclude(is_promo=True, promo_ends__lt=today)
        .select_related("product")
    )
    lowest = {}  # product id -> lowest price in the city
    stores_with = {}  # product id -> number of stores that sell it
    own = []
    for price in city_prices:
        product_id = price.product_id
        lowest[product_id] = min(price.amount, lowest.get(product_id, price.amount))
        stores_with[product_id] = stores_with.get(product_id, 0) + 1
        if price.store_id == store.pk:
            own.append(price)
    # "Cheapest" means something only when another store sells it too.
    cheapest = sorted(
        price.product.name
        for price in own
        if stores_with[price.product_id] > 1 and price.amount == lowest[price.product_id]
    )
    address = ", ".join(
        part for part in [store.district.name if store.district else "", store.address] if part
    )
    context = {
        "store": store.name,
        "city": store.city.name,
        "address": address,
        "products": len(own),
        "cheapest": ", ".join(cheapest[:5]),
    }
    return build_draft(
        Post.Rubric.STORE_NEWS, "new_store", language, store.city, context, [], user
    )
