from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from locations.models import City, Store

from .models import Category, Price, Product
from .services import current_prices, price_history


class PriceTestCase(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Sut", slug="sut")
        self.milk = Product.objects.create(name="Sut", category=category)
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.fergana = City.objects.create(name="Farg'ona", slug="fargona")
        self.baraka = Store.objects.create(name="Baraka", city=self.kokand)
        self.arzon = Store.objects.create(name="Arzon", city=self.kokand)
        self.dehqon = Store.objects.create(name="Dehqon", city=self.fergana)

    def price(self, store, amount, days_ago=0, **extra):
        return Price.objects.create(
            product=self.milk,
            store=store,
            amount=amount,
            recorded_at=timezone.now() - timedelta(days=days_ago),
            **extra,
        )


class CurrentPricesTests(PriceTestCase):
    def summary(self, **kwargs):
        return [
            (row["price"].store.name, int(row["price"].amount), row["cheapest"])
            for row in current_prices(self.milk, **kwargs)
        ]

    def test_uses_newest_price_per_store_and_marks_cheapest(self):
        self.price(self.baraka, 9000, days_ago=5)
        self.price(self.baraka, 13000)
        self.price(self.arzon, 12000)
        self.price(self.dehqon, 12500)
        self.assertEqual(
            self.summary(),
            [("Arzon", 12000, True), ("Dehqon", 12500, False), ("Baraka", 13000, False)],
        )

    def test_equal_lowest_prices_are_all_cheapest(self):
        self.price(self.baraka, 12000)
        self.price(self.arzon, 12000)
        self.price(self.dehqon, 12500)
        self.assertEqual(
            self.summary(),
            [("Arzon", 12000, True), ("Baraka", 12000, True), ("Dehqon", 12500, False)],
        )

    def test_city_filter(self):
        self.price(self.baraka, 13000)
        self.price(self.dehqon, 12500)
        self.assertEqual(self.summary(city=self.kokand), [("Baraka", 13000, True)])

    def test_inactive_stores_are_left_out(self):
        self.price(self.baraka, 13000)
        self.price(self.arzon, 12000)
        self.arzon.is_active = False
        self.arzon.save()
        self.assertEqual(self.summary(), [("Baraka", 13000, True)])

    def test_expired_promo_cannot_be_cheapest(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.price(self.baraka, 13000)
        self.price(self.arzon, 9000, is_promo=True, promo_ends=yesterday)
        rows = current_prices(self.milk)
        self.assertEqual(rows[0]["price"].store, self.arzon)
        self.assertTrue(rows[0]["expired"])
        self.assertFalse(rows[0]["cheapest"])
        self.assertTrue(rows[1]["cheapest"])

    def test_no_prices(self):
        self.assertEqual(current_prices(self.milk), [])


class PriceHistoryTests(PriceTestCase):
    def test_one_line_per_store_with_steps_until_now(self):
        self.price(self.baraka, 12000, days_ago=10)
        self.price(self.baraka, 13000, days_ago=3)
        self.price(self.arzon, 11000, days_ago=1)
        series = price_history(self.milk)
        self.assertEqual(
            [line["label"] for line in series], ["Arzon (Qo'qon)", "Baraka (Qo'qon)"]
        )
        baraka = series[1]["data"]
        # Two changes plus the closing point that repeats the last price.
        self.assertEqual([point["y"] for point in baraka], [12000, 13000, 13000])
        self.assertEqual(sorted(p["x"] for p in baraka), [p["x"] for p in baraka])

    def test_price_older_than_period_becomes_starting_point(self):
        self.price(self.baraka, 10000, days_ago=90)
        self.price(self.baraka, 11000, days_ago=60)
        self.price(self.baraka, 12000, days_ago=5)
        (line,) = price_history(self.milk, days=30)
        self.assertEqual([point["y"] for point in line["data"]], [11000, 12000, 12000])
        period_ms = 30 * 24 * 60 * 60 * 1000
        self.assertAlmostEqual(
            line["data"][-1]["x"] - line["data"][0]["x"], period_ms, delta=5000
        )

    def test_city_filter_and_inactive_stores(self):
        self.price(self.baraka, 12000)
        self.price(self.dehqon, 12500)
        self.arzon.is_active = False
        self.arzon.save()
        self.price(self.arzon, 11000)
        series = price_history(self.milk, city=self.kokand)
        self.assertEqual([line["label"] for line in series], ["Baraka"])

    def test_no_history(self):
        self.assertEqual(price_history(self.milk), [])
