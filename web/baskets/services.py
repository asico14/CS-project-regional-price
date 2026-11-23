"""Basket comparison: what would the whole basket cost in each store?

Rules
-----
* The price of a product in a store is its *current* price (the newest
  row), at the regular price if a promotion has ended.
* A store that sells every product is **complete**; its total is exact.
* A store that misses some products is **incomplete**. Its exact total
  only covers what it sells, so for a fair ranking we also compute an
  *estimated* total that fills each missing product with the average
  price of that product in the other compared stores. Products no compared
  store sells cannot be estimated and are reported separately.
* Ranking: complete stores first (cheapest total first), then incomplete
  stores by fewest missing products, then by estimated total.
* Stores that sell none of the basket's products are left out.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from catalog.models import Price
from locations.models import Store


@dataclass
class Line:
    item: object  # BasketItem
    price: object  # Price
    cost: int


@dataclass
class StoreResult:
    store: Store
    lines: list = field(default_factory=list)
    missing: list = field(default_factory=list)  # BasketItems not sold here
    total: int = 0  # exact: only the products the store sells
    estimated_total: int = 0  # total + estimates for the missing products
    rank: int = 0
    difference: int = 0  # estimated_total minus the winner's estimated_total

    @property
    def is_complete(self):
        return not self.missing


@dataclass
class Comparison:
    basket: object
    results: list
    unavailable: list  # BasketItems that no compared store sells

    @property
    def best(self):
        return self.results[0] if self.results else None


def money(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compare_basket(basket, city=None):
    """Rank the active stores (optionally in one ``city``) for ``basket``."""
    items = list(basket.items.select_related("product"))
    product_ids = [item.product_id for item in items]
    prices = (
        Price.objects.current()
        .filter(product_id__in=product_ids, store__is_active=True)
        .select_related("store__city")
    )
    if city is not None:
        prices = prices.filter(store__city=city)

    # store -> product_id -> Price
    table = {}
    for price in prices:
        table.setdefault(price.store, {})[price.product_id] = price

    averages = {}
    for item in items:
        seen = [
            row[item.product_id].effective_price
            for row in table.values()
            if item.product_id in row
        ]
        if seen:
            averages[item.product_id] = Decimal(sum(seen)) / len(seen)
    unavailable = [item for item in items if item.product_id not in averages]

    results = []
    for store, row in table.items():
        result = StoreResult(store=store)
        estimate = Decimal(0)
        for item in items:
            price = row.get(item.product_id)
            if price is None:
                if item.product_id in averages:
                    result.missing.append(item)
                    estimate += averages[item.product_id] * item.quantity
                continue
            cost = money(price.effective_price * item.quantity)
            result.lines.append(Line(item=item, price=price, cost=cost))
            result.total += cost
        result.estimated_total = result.total + money(estimate)
        results.append(result)

    results.sort(
        key=lambda r: (
            len(r.missing),
            r.estimated_total,
            r.store.city.name,
            r.store.name,
        )
    )
    if results:
        best = results[0].estimated_total
        for position, result in enumerate(results, start=1):
            result.rank = position
            result.difference = result.estimated_total - best
    return Comparison(basket=basket, results=results, unavailable=unavailable)
