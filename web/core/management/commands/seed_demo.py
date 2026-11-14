"""Fill the database with demo data for the Fergana Valley.

Usage:  python manage.py seed_demo

The command is safe to run many times: it only creates what is missing.
All stores and prices are invented for demonstration.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from baskets.models import Basket, BasketItem
from catalog.models import Category, Price, Product
from locations.models import City, District, Store

# city name -> district names
CITIES = {
    "Qo'qon": ["Markaz", "Yangi bozor"],
    "Farg'ona": ["Markaz", "Yormozor"],
    "Andijon": ["Markaz", "Eski shahar"],
    "Namangan": ["Markaz", "Chorsu"],
    "Marg'ilon": ["Markaz", "Ipak yo'li"],
}

# One store with each of these names is created in every city.
STORE_NAMES = ["Baraka Market", "Arzon Savdo", "Dehqon Bozori"]

# category -> list of (name, brand, unit, unit_size, base price in so'm)
CATALOG = {
    "Non va un mahsulotlari": [
        ("Non (buxanka)", "", "pc", "1", 4000),
        ("Bug'doy uni", "Oltin Don", "kg", "2", 16000),
        ("Makaron", "Makfa", "pack", "0.4", 9000),
        ("Guruch (lazer)", "", "kg", "1", 18000),
    ],
    "Sut mahsulotlari": [
        ("Sut 3.2%", "Sof Sut", "l", "1", 13000),
        ("Qatiq", "Sof Sut", "l", "0.5", 7000),
        ("Sariyog' 82%", "Vodiy", "pack", "0.2", 28000),
        ("Tuxum", "", "pack", "10", 16000),
    ],
    "Go'sht mahsulotlari": [
        ("Mol go'shti", "", "kg", "1", 95000),
        ("Tovuq go'shti", "", "kg", "1", 38000),
    ],
    "Meva va sabzavotlar": [
        ("Kartoshka", "", "kg", "1", 6000),
        ("Piyoz", "", "kg", "1", 4000),
        ("Sabzi", "", "kg", "1", 5000),
        ("Pomidor", "", "kg", "1", 12000),
        ("Olma", "", "kg", "1", 14000),
    ],
    "Bakaleya": [
        ("Shakar", "", "kg", "1", 12500),
        ("Paxta yog'i", "Vodiy", "l", "1", 19000),
        ("Kungaboqar yog'i", "Oltin", "l", "1", 24000),
        ("Osh tuzi", "", "kg", "1", 2500),
    ],
    "Ichimliklar": [
        ("Qora choy", "Impra", "pack", "0.1", 11000),
        ("Ko'k choy", "", "pack", "0.1", 8000),
        ("Gazsiz suv", "Vodiy Suv", "l", "1.5", 3500),
    ],
}

# Demo basket: product name -> quantity
DEMO_BASKET = {"Non (buxanka)": 7, "Sut 3.2%": 3, "Shakar": 1, "Kartoshka": 2, "Piyoz": 1}

HISTORY_DAYS = 30
# Fixed seed: every run of the command generates the same demo prices.
RANDOM_SEED = 2026


def round_price(value):
    """Round to 100 so'm, like real shelf prices."""
    return Decimal(max(100, round(value / 100) * 100))


class Command(BaseCommand):
    help = "Create demo locations, catalog, price history and promotions."

    @transaction.atomic
    def handle(self, *args, **options):
        stores = self.seed_locations()
        products = self.seed_catalog()
        self.seed_prices(stores, products)
        self.seed_basket()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {City.objects.count()} cities, "
                f"{len(stores)} stores, {Category.objects.count()} categories, "
                f"{len(products)} products, {Price.objects.count()} prices "
                f"({Price.objects.filter(is_promo=True).count()} promotions)."
            )
        )

    def seed_locations(self):
        stores = []
        for city_name, district_names in CITIES.items():
            city, _ = City.objects.get_or_create(
                slug=slugify(city_name), defaults={"name": city_name}
            )
            districts = [
                District.objects.get_or_create(city=city, name=name)[0]
                for name in district_names
            ]
            for index, store_name in enumerate(STORE_NAMES):
                district = districts[index % len(districts)]
                store, _ = Store.objects.get_or_create(
                    city=city,
                    name=store_name,
                    defaults={
                        "district": district,
                        "address": f"{district.name}, {index + 1}-uy",
                    },
                )
                stores.append(store)
        return stores

    def seed_catalog(self):
        """Create categories and products; return {product: base price}."""
        products = {}
        for category_name, rows in CATALOG.items():
            category, _ = Category.objects.get_or_create(
                slug=slugify(category_name), defaults={"name": category_name}
            )
            for name, brand, unit, unit_size, base_price in rows:
                product, _ = Product.objects.get_or_create(
                    name=name,
                    brand=brand,
                    unit=unit,
                    unit_size=Decimal(unit_size),
                    defaults={"category": category},
                )
                products[product] = base_price
        return products

    def seed_basket(self):
        basket, created = Basket.objects.get_or_create(
            name="Haftalik savat", defaults={"description": "Bir haftalik asosiy mahsulotlar"}
        )
        if created:
            for name, quantity in DEMO_BASKET.items():
                product = Product.objects.filter(name=name).first()
                if product:
                    BasketItem.objects.create(basket=basket, product=product, quantity=quantity)

    def seed_prices(self, stores, products):
        """Generate HISTORY_DAYS of price history and a few promotions.

        Prices are append-only, so history is generated only once: if
        the table already has rows, nothing is added.
        """
        if Price.objects.exists():
            self.stdout.write("Prices already exist - history not generated again.")
            return

        rng = random.Random(RANDOM_SEED)
        now = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        today = timezone.localdate()
        rows = []
        for store in stores:
            # Every store is a little cheaper or more expensive overall.
            store_factor = rng.uniform(0.93, 1.08)
            for product, base_price in products.items():
                # Not every store sells every product.
                if rng.random() < 0.12:
                    continue
                amount = round_price(base_price * store_factor * rng.uniform(0.97, 1.03))
                rows.append(
                    Price(
                        product=product,
                        store=store,
                        amount=amount,
                        recorded_at=now - timedelta(days=HISTORY_DAYS),
                    )
                )
                # A new row is added only on days when the price changes.
                for days_ago in range(HISTORY_DAYS - 1, 0, -1):
                    if rng.random() < 0.12:
                        changed = round_price(float(amount) * rng.uniform(0.95, 1.07))
                        if changed != amount:
                            amount = changed
                            rows.append(
                                Price(
                                    product=product,
                                    store=store,
                                    amount=amount,
                                    recorded_at=now - timedelta(days=days_ago),
                                )
                            )
                # Some products are on promotion right now.
                if rng.random() < 0.08:
                    rows.append(
                        Price(
                            product=product,
                            store=store,
                            amount=round_price(float(amount) * rng.uniform(0.75, 0.9)),
                            recorded_at=now,
                            is_promo=True,
                            promo_ends=today + timedelta(days=rng.randint(3, 7)),
                        )
                    )
        Price.objects.bulk_create(rows)
