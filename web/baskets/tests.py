from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Price, Product
from core.testing import StaffTestCase, make_user
from locations.models import City, Store

from .models import Basket, BasketItem
from .services import compare_basket


class BasketTestData(TestCase):
    """Three products, four stores in two cities."""

    def setUp(self):
        super().setUp()
        food = Category.objects.create(name="Oziq-ovqat", slug="food")
        self.milk = Product.objects.create(name="Sut", category=food)
        self.bread = Product.objects.create(name="Non", category=food)
        self.meat = Product.objects.create(name="Go'sht", category=food, unit="kg")
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.fergana = City.objects.create(name="Farg'ona", slug="fargona")
        self.a = Store.objects.create(name="A", city=self.kokand)
        self.b = Store.objects.create(name="B", city=self.kokand)
        self.c = Store.objects.create(name="C", city=self.fergana)
        self.closed = Store.objects.create(name="Closed", city=self.kokand,
                                           is_active=False)
        self.basket = Basket.objects.create(name="Weekly")
        BasketItem.objects.create(basket=self.basket, product=self.milk, quantity=2)
        BasketItem.objects.create(basket=self.basket, product=self.bread, quantity=3)
        BasketItem.objects.create(basket=self.basket, product=self.meat,
                                  quantity=Decimal("0.5"))

    def price(self, store, product, price, **extra):
        return Price.objects.create(store=store, product=product, price=price,
                                    observed_on=extra.pop("day", date(2026, 11, 1)),
                                    **extra)


class BasketModelTests(BasketTestData):
    def test_str_and_constraints(self):
        item = self.basket.items.get(product=self.meat)
        self.assertEqual(str(item), "0.5 × Go'sht, 1 kg")
        with self.assertRaises(IntegrityError), transaction.atomic():
            BasketItem.objects.create(basket=self.basket, product=self.milk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BasketItem.objects.create(basket=self.basket, product=Product.objects.create(
                name="Suv", category=self.milk.category), quantity=0)


class CompareBasketTests(BasketTestData):
    def test_complete_stores_ranked_by_total(self):
        for store, (milk, bread, meat) in {
            self.a: (10000, 4000, 100000),  # 20000 + 12000 + 50000 = 82000
            self.b: (9000, 4000, 98000),    # 18000 + 12000 + 49000 = 79000
        }.items():
            self.price(store, self.milk, milk)
            self.price(store, self.bread, bread)
            self.price(store, self.meat, meat)
        comparison = compare_basket(self.basket)
        self.assertEqual([r.store for r in comparison.results], [self.b, self.a])
        self.assertEqual([r.total for r in comparison.results], [79000, 82000])
        self.assertEqual([r.difference for r in comparison.results], [0, 3000])
        self.assertEqual([r.rank for r in comparison.results], [1, 2])
        self.assertTrue(all(r.is_complete for r in comparison.results))
        self.assertEqual(comparison.best.store, self.b)

    def test_incomplete_store_ranked_after_complete_one(self):
        # B misses meat: its exact total is lower but it is incomplete.
        self.price(self.a, self.milk, 10000)
        self.price(self.a, self.bread, 4000)
        self.price(self.a, self.meat, 100000)
        self.price(self.b, self.milk, 9000)
        self.price(self.b, self.bread, 3000)
        a, b = compare_basket(self.basket).results
        self.assertEqual(a.store, self.a)
        self.assertEqual([i.product for i in b.missing], [self.meat])
        self.assertEqual(b.total, 27000)
        # Missing meat is estimated at the average of the other stores.
        self.assertEqual(b.estimated_total, 27000 + 50000)
        self.assertFalse(b.is_complete)

    def test_product_sold_nowhere_is_unavailable_not_missing(self):
        self.price(self.a, self.milk, 10000)
        self.price(self.a, self.bread, 4000)
        comparison = compare_basket(self.basket)
        self.assertEqual([i.product for i in comparison.unavailable], [self.meat])
        (result,) = comparison.results
        self.assertTrue(result.is_complete)
        self.assertEqual(result.total, 32000)

    def test_city_filter_inactive_stores_and_newest_price(self):
        self.price(self.a, self.milk, 10000, day=date(2026, 10, 1))
        self.price(self.a, self.milk, 12000, day=date(2026, 11, 1))
        self.price(self.c, self.milk, 1000)
        self.price(self.closed, self.milk, 1)
        results = compare_basket(self.basket, city=self.kokand).results
        self.assertEqual([r.store for r in results], [self.a])
        self.assertEqual(results[0].total, 24000)

    def test_ended_promotion_counts_at_regular_price(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        self.price(self.a, self.milk, 8000, regular_price=10000, promo_until=yesterday)
        self.price(self.b, self.milk, 8000, regular_price=10000)
        a_or_b = {r.store: r.total for r in compare_basket(self.basket).results}
        self.assertEqual(a_or_b, {self.a: 20000, self.b: 16000})

    def test_empty_basket(self):
        empty = Basket.objects.create(name="Empty")
        comparison = compare_basket(empty)
        self.assertEqual(comparison.results, [])
        self.assertIsNone(comparison.best)


class BasketPageTests(BasketTestData):
    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client.force_login(self.user)

    def formset_data(self, rows, initial=0):
        data = {
            "items-TOTAL_FORMS": str(len(rows)),
            "items-INITIAL_FORMS": str(initial),
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
        }
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f"items-{i}-{key}"] = value
        return data

    def test_pages_are_staff_only(self):
        for url in [reverse("baskets:basket_list"), reverse("baskets:basket_create"),
                    reverse("baskets:basket_compare", args=[self.basket.pk])]:
            StaffTestCase.assertStaffOnly(self, url)

    def test_create_basket_with_items(self):
        data = {"name": "Nonushta", "description": "", "is_active": "on"}
        data.update(self.formset_data([
            {"product": self.milk.pk, "quantity": "1"},
            {"product": self.bread.pk, "quantity": "2"},
            {"product": "", "quantity": "1"},  # untouched extra row is ignored
        ]))
        response = self.client.post(reverse("baskets:basket_create"), data)
        basket = Basket.objects.get(name="Nonushta")
        self.assertRedirects(response, reverse("baskets:basket_compare", args=[basket.pk]))
        self.assertEqual(basket.items.count(), 2)
        self.assertEqual(basket.created_by, self.user)

    def test_edit_removes_and_changes_items(self):
        items = list(self.basket.items.order_by("id"))
        data = {"name": "Weekly", "description": "", "is_active": "on"}
        data.update(self.formset_data([
            {"id": items[0].pk, "product": self.milk.pk, "quantity": "5"},
            {"id": items[1].pk, "product": self.bread.pk, "quantity": "3", "DELETE": "on"},
            {"id": items[2].pk, "product": self.meat.pk, "quantity": "0.5"},
        ], initial=3))
        url = reverse("baskets:basket_edit", args=[self.basket.pk])
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(
            {(i.product, i.quantity) for i in self.basket.items.all()},
            {(self.milk, 5), (self.meat, Decimal("0.5"))},
        )

    def test_duplicate_product_is_rejected(self):
        data = {"name": "Dup", "description": ""}
        data.update(self.formset_data([
            {"product": self.milk.pk, "quantity": "1"},
            {"product": self.milk.pk, "quantity": "2"},
        ]))
        response = self.client.post(reverse("baskets:basket_create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Basket.objects.filter(name="Dup").exists())

    def test_compare_page_ranks_and_filters_by_city(self):
        self.price(self.a, self.milk, 10000)
        self.price(self.c, self.milk, 9000)
        url = reverse("baskets:basket_compare", args=[self.basket.pk])
        response = self.client.get(url)
        self.assertEqual([r.store for r in response.context["comparison"].results],
                         [self.c, self.a])
        self.assertContains(response, "best")
        response = self.client.get(url, {"city": "qoqon"})
        self.assertEqual([r.store for r in response.context["comparison"].results],
                         [self.a])
        self.assertEqual(self.client.get(url, {"city": "nowhere"}).status_code, 404)
