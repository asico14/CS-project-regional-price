"""Price calculations used by the pages (kept out of the views so they
can be tested on their own)."""

from .models import Price


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
