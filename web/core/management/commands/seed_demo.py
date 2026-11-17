"""Fill the database with demo data for the Fergana Valley.

    python manage.py seed_demo

The command is idempotent: running it again does not create duplicates.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Category, Product
from locations.models import City, District, Store

# slug: (name, [districts])
CITIES = {
    "qoqon": ("Qo'qon", ["Markaz", "Navbahor", "Ibrat"]),
    "fargona": ("Farg'ona", ["Markaz", "Yangi Farg'ona", "Kirgili"]),
    "andijon": ("Andijon", ["Markaz", "Bobur", "Eski shahar"]),
    "namangan": ("Namangan", ["Markaz", "Davlatobod", "Chorsu"]),
    "margilon": ("Marg'ilon", ["Markaz", "Toshloq yo'li"]),
}

# (store name, city slug, district, address)
STORES = [
    ("Korzinka", "qoqon", "Markaz", "Turkiston ko'chasi 12"),
    ("Makro", "qoqon", "Navbahor", "Navbahor ko'chasi 5"),
    ("Qo'qon dehqon bozori", "qoqon", "Ibrat", "Ibrat ko'chasi 1"),
    ("Korzinka", "fargona", "Markaz", "Al-Farg'oniy ko'chasi 20"),
    ("Havas", "fargona", "Yangi Farg'ona", "Mustaqillik ko'chasi 44"),
    ("Farg'ona markaziy bozori", "fargona", "Kirgili", "Kirgili ko'chasi 3"),
    ("Korzinka", "andijon", "Bobur", "Bobur shoh ko'chasi 9"),
    ("Makro", "andijon", "Markaz", "Navoiy shoh ko'chasi 17"),
    ("Jahon bozori", "andijon", "Eski shahar", "Eski shahar 2"),
    ("Havas", "namangan", "Davlatobod", "Davlatobod 7"),
    ("Makro", "namangan", "Markaz", "Islom Karimov ko'chasi 30"),
    ("Chorsu bozori", "namangan", "Chorsu", "Chorsu maydoni"),
    ("Korzinka", "margilon", "Markaz", "Burhoniddin Marg'iloniy ko'chasi 4"),
    ("Marg'ilon dehqon bozori", "margilon", "Toshloq yo'li", "Toshloq yo'li 11"),
]

# slug: name
CATEGORIES = {
    "sut": "Sut mahsulotlari",
    "non": "Non va un mahsulotlari",
    "gosht": "Go'sht",
    "sabzavot": "Sabzavot va mevalar",
    "yog": "Yog' va shakar",
    "ichimlik": "Ichimliklar",
    "maishiy": "Maishiy kimyo",
}

# (name, brand, category slug, unit, unit size, base price in so'm)
PRODUCTS = [
    ("Sut 3.2%", "Nestle", "sut", "l", "0.9", 13500),
    ("Sut 2.5%", "Musaffo", "sut", "l", "1", 11000),
    ("Qatiq", "Musaffo", "sut", "l", "0.5", 7000),
    ("Tuxum", "", "sut", "pc", "10", 16000),
    ("Smetana 20%", "Lactel", "sut", "kg", "0.4", 15000),
    ("Non (patir)", "", "non", "pc", "1", 4000),
    ("Un oliy nav", "Kamolon", "non", "kg", "2", 18000),
    ("Guruch lazer", "", "non", "kg", "1", 22000),
    ("Makaron", "Makfa", "non", "kg", "0.45", 9500),
    ("Mol go'shti", "", "gosht", "kg", "1", 105000),
    ("Qo'y go'shti", "", "gosht", "kg", "1", 115000),
    ("Tovuq go'shti", "", "gosht", "kg", "1", 38000),
    ("Kartoshka", "", "sabzavot", "kg", "1", 5000),
    ("Piyoz", "", "sabzavot", "kg", "1", 4000),
    ("Sabzi", "", "sabzavot", "kg", "1", 4500),
    ("Pomidor", "", "sabzavot", "kg", "1", 12000),
    ("Olma", "", "sabzavot", "kg", "1", 14000),
    ("Paxta yog'i", "Oltin", "yog", "l", "1", 24000),
    ("Shakar", "", "yog", "kg", "1", 13000),
    ("Choy ko'k", "Shoh", "ichimlik", "pack", "0.1", 9000),
    ("Coca-Cola", "Coca-Cola", "ichimlik", "l", "1.5", 12000),
    ("Suv", "Hydrolife", "ichimlik", "l", "1.5", 3500),
    ("Kir yuvish kukuni", "Ariel", "maishiy", "kg", "3", 89000),
    ("Idish yuvish vositasi", "Fairy", "maishiy", "l", "0.45", 16000),
]


class Command(BaseCommand):
    help = "Create demo cities, stores, categories and products."

    @transaction.atomic
    def handle(self, *args, **options):
        cities = self.seed_locations()
        products = self.seed_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Locations: {len(cities)} cities, {Store.objects.count()} stores. "
                f"Catalog: {Category.objects.count()} categories, "
                f"{len(products)} products."
            )
        )

    def seed_locations(self):
        cities = {}
        for slug, (name, districts) in CITIES.items():
            city, _ = City.objects.get_or_create(slug=slug, defaults={"name": name})
            cities[slug] = city
            for district in districts:
                District.objects.get_or_create(city=city, name=district)
        for name, city_slug, district, address in STORES:
            city = cities[city_slug]
            Store.objects.get_or_create(
                city=city,
                name=name,
                address=address,
                defaults={"district": District.objects.get(city=city, name=district)},
            )
        return cities

    def seed_catalog(self):
        categories = {
            slug: Category.objects.get_or_create(slug=slug, defaults={"name": name})[0]
            for slug, name in CATEGORIES.items()
        }
        products = {}
        for name, brand, category, unit, size, base_price in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                name=name,
                brand=brand,
                unit=unit,
                unit_size=Decimal(size),
                defaults={"category": categories[category]},
            )
            products[product] = base_price
        return products
