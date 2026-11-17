from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Category, Price, Product


class CatalogModelTests(TestCase):
    def setUp(self):
        self.dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")

    def test_str(self):
        milk = Product.objects.create(
            name="Sut 3.2%",
            brand="Nestle",
            category=self.dairy,
            unit=Product.Unit.LITRE,
            unit_size=Decimal("0.900"),
        )
        milk.refresh_from_db()
        self.assertEqual(str(self.dairy), "Sut mahsulotlari")
        self.assertEqual(str(milk), "Sut 3.2%, Nestle, 0.9 litre")

    def test_defaults(self):
        eggs = Product.objects.create(name="Tuxum", category=self.dairy)
        eggs.refresh_from_db()
        self.assertEqual(eggs.unit, Product.Unit.PIECE)
        self.assertEqual(eggs.unit_size, 1)
        self.assertTrue(eggs.is_active)
        self.assertEqual(str(eggs), "Tuxum, 1 piece")

    def test_same_product_in_other_size_is_allowed_but_duplicate_is_not(self):
        Product.objects.create(name="Sut", category=self.dairy, unit="l", unit_size=1)
        Product.objects.create(name="Sut", category=self.dairy, unit="l", unit_size=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(
                name="Sut", category=self.dairy, unit="l", unit_size=1
            )

    def test_unit_size_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(name="Sut", category=self.dairy, unit_size=0)

    def test_category_with_products_cannot_be_deleted(self):
        Product.objects.create(name="Sut", category=self.dairy)
        with self.assertRaises(ProtectedError):
            self.dairy.delete()


class PriceModelTests(TestCase):
    def setUp(self):
        from locations.models import City, Store

        dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")
        self.milk = Product.objects.create(
            name="Sut", category=dairy, unit="l", unit_size=Decimal("0.5")
        )
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        self.store_a = Store.objects.create(name="Korzinka", city=city)
        self.store_b = Store.objects.create(name="Makro", city=city)

    def add(self, store, price, day, **extra):
        return Price.objects.create(
            product=self.milk, store=store, price=price,
            observed_on=date(2026, 11, day), **extra,
        )

    def test_prices_cannot_be_changed(self):
        price = self.add(self.store_a, 6000, 1)
        price.price = 5000
        with self.assertRaises(ValueError):
            price.save()

    def test_current_returns_newest_price_per_store(self):
        self.add(self.store_a, 6000, 1)
        newest_a = self.add(self.store_a, 6500, 3)
        self.add(self.store_b, 7000, 2)
        newest_b = self.add(self.store_b, 6900, 2)  # same day: later row wins
        current = set(Price.objects.current())
        self.assertEqual(current, {newest_a, newest_b})

    def test_unit_price_and_discount(self):
        price = self.add(self.store_a, 6000, 1, regular_price=8000)
        self.assertEqual(price.unit_price, 12000)
        self.assertEqual(price.discount_percent, 25)
        self.assertTrue(price.is_promotion)

    def test_expired_promotion_is_not_a_promotion(self):
        price = self.add(
            self.store_a, 6000, 1, regular_price=8000, promo_until=date(2000, 1, 1)
        )
        self.assertFalse(price.is_promotion)

    def test_regular_price_must_be_higher(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add(self.store_a, 6000, 1, regular_price=6000)
        with self.assertRaises(ValidationError):
            Price(product=self.milk, store=self.store_a, price=6000,
                  regular_price=5000).clean()

    def test_store_with_prices_cannot_be_deleted(self):
        self.add(self.store_a, 6000, 1)
        with self.assertRaises(ProtectedError):
            self.store_a.delete()
