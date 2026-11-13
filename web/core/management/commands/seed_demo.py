"""Fill the database with demo data for the Fergana Valley.

Usage:  python manage.py seed_demo

The command is safe to run many times: it only creates what is missing.
All stores and prices are invented for demonstration.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Category, Product
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


class Command(BaseCommand):
    help = "Create demo cities, districts, stores, categories and products."

    @transaction.atomic
    def handle(self, *args, **options):
        stores = self.seed_locations()
        products = self.seed_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {City.objects.count()} cities, "
                f"{len(stores)} stores, {Category.objects.count()} categories, "
                f"{len(products)} products."
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
