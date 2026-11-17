from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.testing import StaffTestCase

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


class ProductListTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")
        meat = Category.objects.create(name="Go'sht", slug="gosht")
        Product.objects.create(name="Sut", brand="Nestle", category=dairy)
        Product.objects.create(name="Qatiq", brand="Musaffo", category=dairy)
        Product.objects.create(name="Mol go'shti", category=meat)
        Product.objects.create(name="Eski sut", category=dairy, is_active=False)
        self.url = reverse("catalog:product_list")

    def names(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200)
        return {p.name for p in response.context["product_list"]}

    def test_staff_only(self):
        self.assertStaffOnly(self.url)

    def test_lists_active_products(self):
        self.assertEqual(self.names(), {"Sut", "Qatiq", "Mol go'shti"})

    def test_search_matches_name_and_brand(self):
        self.assertEqual(self.names(q="sut"), {"Sut"})
        self.assertEqual(self.names(q="musaffo"), {"Qatiq"})

    def test_category_filter_and_inactive(self):
        self.assertEqual(self.names(category="gosht"), {"Mol go'shti"})
        self.assertEqual(self.names(q="sut", inactive="1"), {"Sut", "Eski sut"})


class ProductFormTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")

    def data(self, **extra):
        data = {"name": "  Sut   3.2% ", "brand": "Nestle", "category": self.dairy.pk,
                "unit": "l", "unit_size": "0.9", "is_active": "on"}
        data.update(extra)
        return data

    def test_staff_only(self):
        self.assertStaffOnly(reverse("catalog:product_create"))

    def test_create_and_edit(self):
        response = self.client.post(reverse("catalog:product_create"), self.data())
        self.assertRedirects(response, reverse("catalog:product_list"))
        product = Product.objects.get()
        self.assertEqual(product.name, "Sut 3.2%")  # whitespace normalised
        url = reverse("catalog:product_edit", args=[product.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, self.data(unit_size="1", is_active=""))
        self.assertEqual(Product.objects.count(), 1)
        product.refresh_from_db()
        self.assertEqual(product.unit_size, 1)
        self.assertFalse(product.is_active)

    def test_duplicate_and_invalid_size_are_rejected(self):
        self.client.post(reverse("catalog:product_create"), self.data())
        response = self.client.post(reverse("catalog:product_create"), self.data())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        response = self.client.post(
            reverse("catalog:product_create"), self.data(unit_size="0")
        )
        self.assertIn("unit_size", response.context["form"].errors)
        self.assertEqual(Product.objects.count(), 1)


class PriceEntryTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        from locations.models import City, Store

        dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")
        self.milk = Product.objects.create(name="Sut", category=dairy)
        self.kefir = Product.objects.create(name="Qatiq", category=dairy)
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        self.store = Store.objects.create(name="Korzinka", city=city)
        self.url = (
            reverse("catalog:price_entry")
            + f"?store={self.store.pk}&observed_on=2026-11-01"
        )

    def test_staff_only(self):
        self.assertStaffOnly(reverse("catalog:price_entry"))

    def test_start_page_and_future_date(self):
        response = self.client.get(reverse("catalog:price_entry"))
        self.assertTemplateUsed(response, "catalog/price_entry_start.html")
        response = self.client.get(
            reverse("catalog:price_entry"),
            {"store": self.store.pk, "observed_on": "2999-01-01"},
        )
        self.assertTemplateUsed(response, "catalog/price_entry_start.html")

    def test_last_price_is_shown(self):
        Price.objects.create(product=self.milk, store=self.store, price=9000,
                             observed_on=date(2026, 10, 30))
        response = self.client.get(self.url)
        rows = {r["product"]: r["last_price"] for r in response.context["form"].rows}
        self.assertEqual(rows, {self.milk: 9000, self.kefir: None})

    def test_only_filled_rows_are_saved(self):
        response = self.client.post(self.url, {
            f"price_{self.milk.pk}": "9500",
            f"price_{self.kefir.pk}": "6000",
            f"regular_{self.kefir.pk}": "7000",
            f"until_{self.kefir.pk}": "2026-11-05",
        })
        self.assertEqual(response.status_code, 302)
        milk = Price.objects.get(product=self.milk)
        self.assertEqual((milk.price, milk.observed_on), (9500, date(2026, 11, 1)))
        self.assertEqual(milk.created_by, self.user)
        kefir = Price.objects.get(product=self.kefir)
        self.assertEqual(kefir.regular_price, 7000)

    def test_invalid_promo_saves_nothing(self):
        response = self.client.post(self.url, {
            f"price_{self.milk.pk}": "9500",
            f"price_{self.kefir.pk}": "6000",
            f"regular_{self.kefir.pk}": "5000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"regular_{self.kefir.pk}", response.context["form"].errors)
        self.assertFalse(Price.objects.exists())

    def test_empty_form_saves_nothing(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Price.objects.exists())
