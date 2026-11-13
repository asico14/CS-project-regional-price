"""Basket comparison: what does the same basket cost in each store?"""

from dataclasses import dataclass, field
from decimal import Decimal

from catalog.models import Price


@dataclass
class BasketLine:
    item: object  # BasketItem
    price: object = None  # Price, or None when the store has no valid price
    total: Decimal = Decimal("0")


@dataclass
class StoreResult:
    store: object
    lines: list = field(default_factory=list)
    total: Decimal = Decimal("0")
    missing: list = field(default_factory=list)  # products without a price
    rank: int = None  # 1 = cheapest; only complete baskets are ranked
    extra: Decimal = None  # how much more than the cheapest store

    @property
    def complete(self):
        return not self.missing


def compare_basket(basket, city=None):
    """Return a list of StoreResult, best store first.

    Missing products: a store that has no valid price for some product
    cannot be compared fairly, because its total would look cheaper
    only because something is not counted. So:

    * stores with every product ("complete") are ranked by total;
    * incomplete stores come after them, are not ranked, and show which
      products are missing and the total of what they do have;
    * stores with none of the products are left out.

    A promo price whose end date has passed counts as missing.
    """
    items = list(basket.items.select_related("product"))
    if not items:
        return []

    prices = (
        Price.objects.current()
        .filter(product__in=[item.product for item in items], store__is_active=True)
        .select_related("store", "store__city")
    )
    if city is not None:
        prices = prices.filter(store__city=city)

    stores = {}
    valid = {}  # (store id, product id) -> Price
    for price in prices:
        stores[price.store_id] = price.store
        if price.is_promo and not price.is_active_promo:
            continue
        valid[(price.store_id, price.product_id)] = price

    results = []
    for store in stores.values():
        result = StoreResult(store=store)
        for item in items:
            price = valid.get((store.pk, item.product_id))
            if price is None:
                result.lines.append(BasketLine(item=item))
                result.missing.append(item.product)
            else:
                line_total = (price.amount * item.quantity).quantize(Decimal("0.01"))
                result.lines.append(BasketLine(item=item, price=price, total=line_total))
                result.total += line_total
        if len(result.missing) < len(items):
            results.append(result)

    complete = sorted(
        (result for result in results if result.complete),
        key=lambda result: (result.total, result.store.name),
    )
    incomplete = sorted(
        (result for result in results if not result.complete),
        key=lambda result: (len(result.missing), result.total, result.store.name),
    )
    for position, result in enumerate(complete, start=1):
        # Equal totals share the same place.
        same_as_previous = position > 1 and complete[position - 2].total == result.total
        result.rank = complete[position - 2].rank if same_as_previous else position
        result.extra = result.total - complete[0].total
    return complete + incomplete
