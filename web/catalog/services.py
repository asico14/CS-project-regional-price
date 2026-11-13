"""Price calculations used by the pages (kept out of the views so they
can be tested on their own)."""

from datetime import timedelta

from django.utils import timezone

from .models import Price

HISTORY_DAYS = 30


def current_prices(product, city=None):
    """Current price of the product in every active store, cheapest first.

    Returns a list of dicts: {"price", "expired", "cheapest"}.
    A promo price whose end date has passed is marked as expired: it is
    still shown, but it is no longer valid, so it cannot be the cheapest.
    """
    prices = (
        Price.objects.current()
        .filter(product=product, store__is_active=True)
        .select_related("store", "store__city")
        .order_by("amount", "store__name")
    )
    if city is not None:
        prices = prices.filter(store__city=city)

    rows = [
        {
            "price": price,
            "expired": price.is_promo and not price.is_active_promo,
            "cheapest": False,
        }
        for price in prices
    ]
    valid_amounts = [row["price"].amount for row in rows if not row["expired"]]
    if valid_amounts:
        lowest = min(valid_amounts)
        for row in rows:
            # Stores with the same lowest price are all highlighted.
            row["cheapest"] = not row["expired"] and row["price"].amount == lowest
    return rows


def price_history(product, city=None, days=HISTORY_DAYS):
    """Price history of the product for the chart: one line per store.

    Returns a list of {"label": store name, "data": [{"x": ms, "y": price}]}
    where x is a JavaScript timestamp. Every line starts at the price
    that was valid at the beginning of the period and ends at "now", so
    a store whose price did not change is drawn as a flat line.
    """
    now = timezone.now()
    start = now - timedelta(days=days)
    prices = (
        Price.objects.filter(product=product, store__is_active=True)
        .select_related("store", "store__city")
        .order_by("recorded_at", "id")
    )
    if city is not None:
        prices = prices.filter(store__city=city)

    def point(moment, amount):
        return {"x": int(moment.timestamp() * 1000), "y": float(amount)}

    lines = {}
    for price in prices:
        if price.recorded_at > now:
            continue
        line = lines.setdefault(price.store_id, {"store": price.store, "data": []})
        if price.recorded_at <= start:
            # Older than the period: keep only the last one, moved to
            # the start, as the price the period begins with.
            line["data"] = [point(start, price.amount)]
        else:
            line["data"].append(point(price.recorded_at, price.amount))

    series = []
    for line in lines.values():
        line["data"].append({"x": int(now.timestamp() * 1000), "y": line["data"][-1]["y"]})
        store = line["store"]
        label = store.name if city is not None else f"{store.name} ({store.city.name})"
        series.append({"label": label, "data": line["data"]})
    return sorted(series, key=lambda item: item["label"])
