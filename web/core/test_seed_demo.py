from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from baskets.models import Basket
from catalog.models import Category, Price, Product
from locations.models import City, District, Store


def counts():
    models = (City, District, Store, Category, Product, Price, Basket)
    return [model.objects.count() for model in models]


class SeedDemoTests(TestCase):
    def test_creates_demo_data(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(counts()[:5], [5, 10, 15, 6, 22])
        for store in Store.objects.all():
            store.full_clean()
        basket = Basket.objects.get(name="Haftalik savat")
        self.assertEqual(basket.items.count(), 5)

    def test_running_twice_creates_nothing_new(self):
        call_command("seed_demo", stdout=StringIO())
        first = counts()
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(counts(), first)

    def test_generates_price_history_and_promotions(self):
        call_command("seed_demo", stdout=StringIO())
        store = Store.objects.first()
        product = store.prices.first().product
        history = Price.objects.filter(store=store, product=product)
        self.assertGreaterEqual(history.count(), 1)
        # Most products have more than one price row in at least one store.
        self.assertGreater(Price.objects.count(), 15 * 22)
        promotions = Price.objects.filter(is_promo=True)
        self.assertTrue(promotions.exists())
        for promo in promotions:
            self.assertTrue(promo.is_active_promo)
            promo.full_clean()
