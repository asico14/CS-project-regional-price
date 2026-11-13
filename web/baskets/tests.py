from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from catalog.models import Category, Price, Product
from locations.models import City, Store

from .models import Basket, BasketItem
from .services import compare_basket


class BasketTestCase(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Oziq-ovqat", slug="oziq-ovqat")
        self.milk = Product.objects.create(name="Sut", category=category)
        self.bread = Product.objects.create(name="Non", category=category)
        self.sugar = Product.objects.create(name="Shakar", category=category)
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.fergana = City.objects.create(name="Farg'ona", slug="fargona")
        self.baraka = Store.objects.create(name="Baraka", city=self.kokand)
        self.arzon = Store.objects.create(name="Arzon", city=self.kokand)
        self.dehqon = Store.objects.create(name="Dehqon", city=self.fergana)
        self.basket = Basket.objects.create(name="Haftalik savat")
        BasketItem.objects.create(basket=self.basket, product=self.milk, quantity=2)
        BasketItem.objects.create(basket=self.basket, product=self.bread, quantity=3)

    def price(self, store, product, amount, **extra):
        return Price.objects.create(
            product=product, store=store, amount=amount, **extra
        )

    def fill(self, store, milk, bread):
        self.price(store, self.milk, milk)
        self.price(store, self.bread, bread)


class BasketModelTests(BasketTestCase):
    def test_str(self):
        self.assertEqual(str(self.basket), "Haftalik savat")
        self.assertEqual(str(self.basket.items.get(product=self.milk)), "2 × Sut, 1 piece")

    def test_product_only_once_per_basket(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BasketItem.objects.create(basket=self.basket, product=self.milk)

    def test_quantity_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BasketItem.objects.create(
                basket=self.basket, product=self.sugar, quantity=0
            )


class CompareBasketTests(BasketTestCase):
    def summary(self, **kwargs):
        return [
            (result.store.name, int(result.total), result.rank)
            for result in compare_basket(self.basket, **kwargs)
        ]

    def test_totals_use_quantities_and_rank_cheapest_first(self):
        self.fill(self.baraka, milk=13000, bread=4000)  # 26000 + 12000
        self.fill(self.arzon, milk=12000, bread=4500)  # 24000 + 13500
        self.fill(self.dehqon, milk=14000, bread=4000)  # 28000 + 12000
        self.assertEqual(
            self.summary(),
            [("Arzon", 37500, 1), ("Baraka", 38000, 2), ("Dehqon", 40000, 3)],
        )
        results = compare_basket(self.basket)
        self.assertEqual([int(result.extra) for result in results], [0, 500, 2500])
        self.assertEqual(results[0].lines[1].total, Decimal("24000.00"))

    def test_newest_price_is_used(self):
        self.fill(self.baraka, milk=99000, bread=99000)
        self.fill(self.baraka, milk=13000, bread=4000)
        self.assertEqual(self.summary(), [("Baraka", 38000, 1)])

    def test_store_with_missing_product_is_not_ranked(self):
        self.fill(self.baraka, milk=13000, bread=4000)
        # Arzon looks cheaper only because it has no bread.
        self.price(self.arzon, self.milk, 12000)
        results = compare_basket(self.basket)
        self.assertEqual(
            self.summary(), [("Baraka", 38000, 1), ("Arzon", 24000, None)]
        )
        self.assertTrue(results[0].complete)
        self.assertFalse(results[1].complete)
        self.assertEqual(results[1].missing, [self.bread])
        self.assertIsNone(results[1].extra)

    def test_incomplete_stores_are_ordered_by_number_missing(self):
        BasketItem.objects.create(basket=self.basket, product=self.sugar)
        self.price(self.baraka, self.milk, 13000)
        self.fill(self.arzon, milk=12000, bread=4500)
        self.assertEqual(
            self.summary(), [("Arzon", 37500, None), ("Baraka", 26000, None)]
        )

    def test_store_with_no_basket_products_is_left_out(self):
        self.fill(self.baraka, milk=13000, bread=4000)
        self.price(self.arzon, self.sugar, 12000)
        self.assertEqual(self.summary(), [("Baraka", 38000, 1)])

    def test_expired_promo_counts_as_missing(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.fill(self.baraka, milk=13000, bread=4000)
        self.price(self.arzon, self.bread, 4000)
        self.price(self.arzon, self.milk, 5000, is_promo=True, promo_ends=yesterday)
        results = compare_basket(self.basket)
        self.assertEqual(results[1].store, self.arzon)
        self.assertEqual(results[1].missing, [self.milk])

    def test_active_promo_price_is_used(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.fill(self.baraka, milk=13000, bread=4000)
        self.price(self.baraka, self.milk, 10000, is_promo=True, promo_ends=tomorrow)
        self.assertEqual(self.summary(), [("Baraka", 32000, 1)])

    def test_equal_totals_share_a_rank(self):
        self.fill(self.baraka, milk=13000, bread=4000)
        self.fill(self.arzon, milk=13000, bread=4000)
        self.fill(self.dehqon, milk=14000, bread=4000)
        self.assertEqual([rank for _, _, rank in self.summary()], [1, 1, 3])

    def test_city_filter_and_inactive_stores(self):
        self.fill(self.baraka, milk=13000, bread=4000)
        self.fill(self.arzon, milk=12000, bread=4000)
        self.fill(self.dehqon, milk=11000, bread=4000)
        self.arzon.is_active = False
        self.arzon.save()
        self.assertEqual(self.summary(city=self.kokand), [("Baraka", 38000, 1)])

    def test_empty_basket_and_no_prices(self):
        self.assertEqual(compare_basket(self.basket), [])
        self.assertEqual(compare_basket(Basket.objects.create(name="Bo'sh")), [])
