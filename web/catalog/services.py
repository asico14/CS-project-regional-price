"""Price calculations used by the pages and the post generators."""

from datetime import timedelta

from django.utils import timezone

from .models import Price


def price_history(product, days=90, city_slug=""):
    """Chart data: one series per store over the last ``days`` days.

    A price stays valid until a new one is observed, so every series is
    "filled forward": on days without an observation the store keeps its
    previous price. The last price seen before the window starts is used
    as the starting value, so lines do not begin empty.

    Returns ``{"labels": ["2026-11-01", ...], "datasets": [{"label": ...,
    "data": [price or None, ...]}, ...]}``, ready for Chart.js.
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    prices = (
        Price.objects.filter(product=product, store__is_active=True)
        .select_related("store__city")
        .order_by("observed_on", "created_at", "id")
    )
    if city_slug:
        prices = prices.filter(store__city__slug=city_slug)

    labels = [start + timedelta(days=i) for i in range(days)]
    # store -> {day: price}; days before the window collapse onto ``start``.
    by_store = {}
    for price in prices:
        day = max(price.observed_on, start)
        by_store.setdefault(price.store, {})[day] = price.price

    datasets = []
    for store, observed in sorted(
        by_store.items(), key=lambda item: (item[0].city.name, item[0].name)
    ):
        data, current = [], None
        for day in labels:
            current = observed.get(day, current)
            data.append(current)
        datasets.append({"label": f"{store.name} ({store.city.name})", "data": data})
    return {"labels": [day.isoformat() for day in labels], "datasets": datasets}
