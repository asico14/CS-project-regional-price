from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Category, Product


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
