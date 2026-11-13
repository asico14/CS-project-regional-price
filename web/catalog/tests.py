from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

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
        self.store = Store.objects.create(name="Korzinka", city=city)

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
