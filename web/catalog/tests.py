from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from locations.models import City, Store

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

    def test_str_works_before_saving(self):
        self.assertEqual(str(Product(name="Non", unit_size=2)), "Non, 2 piece")
        self.assertEqual(str(Product(name="Non", unit_size="0.50")), "Non, 0.5 piece")

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
        category = Category.objects.create(name="Sut mahsulotlari", slug="sut")
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        self.milk = Product.objects.create(name="Sut", category=category)
        self.store = Store.objects.create(name="Baraka", city=city)

    def add_price(self, amount):
        return Price.objects.create(product=self.milk, store=self.store, amount=amount)

    def test_new_price_keeps_old_one(self):
        self.add_price(12000)
        newest = self.add_price(13500)
        self.assertEqual(Price.objects.count(), 2)
        self.assertEqual(self.milk.prices.latest(), newest)
        self.assertEqual(self.milk.prices.first(), newest)

    def test_price_cannot_be_edited(self):
        price = self.add_price(12000)
        price.amount = 1
        with self.assertRaises(ValidationError):
            price.save()
        with self.assertRaises(ValidationError):
            Price.objects.update(amount=1)
        price.refresh_from_db()
        self.assertEqual(price.amount, 12000)

    def test_price_cannot_be_deleted(self):
        price = self.add_price(12000)
        with self.assertRaises(ValidationError):
            price.delete()
        with self.assertRaises(ValidationError):
            Price.objects.all().delete()
        self.assertEqual(Price.objects.count(), 1)

    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.add_price(0)

    def test_product_and_store_with_prices_cannot_be_deleted(self):
        self.add_price(12000)
        with self.assertRaises(ProtectedError):
            self.milk.delete()
        with self.assertRaises(ProtectedError):
            self.store.delete()

    def test_promo_is_active_until_its_end_date(self):
        today = timezone.localdate()
        regular = self.add_price(12000)
        open_ended = Price(product=self.milk, store=self.store, amount=1, is_promo=True)
        running = Price(is_promo=True, promo_ends=today)
        finished = Price(is_promo=True, promo_ends=today - timedelta(days=1))
        self.assertFalse(regular.is_active_promo)
        self.assertTrue(open_ended.is_active_promo)
        self.assertTrue(running.is_active_promo)
        self.assertFalse(finished.is_active_promo)

    def test_end_date_requires_promo_flag(self):
        price = Price(
            product=self.milk,
            store=self.store,
            amount=10000,
            promo_ends=timezone.localdate(),
        )
        with self.assertRaises(ValidationError):
            price.full_clean()

    def test_str(self):
        price = self.add_price(12000)
        self.assertEqual(str(price), "Sut, 1 piece @ Baraka (Qo'qon): 12000 so'm")
