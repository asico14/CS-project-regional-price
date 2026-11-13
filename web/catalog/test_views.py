from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from locations.models import City, Store

from .models import Category, Price, Product


class StaffTestCase(TestCase):
    """Base class: logs in a staff user and creates a small catalog."""

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            "staff", password="pw", is_staff=True
        )
        self.client.force_login(self.staff)
        self.dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")
        self.grocery = Category.objects.create(name="Bakaleya", slug="bakaleya")
        self.milk = Product.objects.create(
            name="Sut 3.2%", brand="Sof Sut", category=self.dairy
        )
        self.sugar = Product.objects.create(name="Shakar", category=self.grocery)


class ProductListTests(StaffTestCase):
    url = reverse("product_list")

    def names(self, **params):
        response = self.client.get(self.url, params)
        return [product.name for product in response.context["products"]]

    def test_requires_staff(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), "/login/?next=/products/")

    def test_lists_all_products(self):
        self.assertEqual(self.names(), ["Shakar", "Sut 3.2%"])

    def test_search_by_name_or_brand(self):
        self.assertEqual(self.names(q="shak"), ["Shakar"])
        self.assertEqual(self.names(q="Sof"), ["Sut 3.2%"])
        self.assertEqual(self.names(q="zzz"), [])

    def test_filter_by_category(self):
        self.assertEqual(self.names(category=self.dairy.pk), ["Sut 3.2%"])
        self.assertEqual(self.names(category=self.dairy.pk, q="shakar"), [])
        # A broken category value is ignored instead of crashing.
        self.assertEqual(len(self.names(category="abc")), 2)

    def test_pagination_keeps_filters(self):
        for number in range(30):
            Product.objects.create(name=f"Choy {number:02}", category=self.grocery)
        response = self.client.get(self.url, {"q": "Choy"})
        self.assertEqual(len(response.context["products"]), 25)
        self.assertContains(response, "?q=Choy&amp;page=2")


class ProductFormTests(StaffTestCase):
    def form_data(self, **changes):
        data = {
            "name": "Qatiq",
            "brand": "Sof Sut",
            "category": self.dairy.pk,
            "unit": "l",
            "unit_size": "0.5",
            "is_active": "on",
        }
        data.update(changes)
        return data

    def test_requires_staff(self):
        self.client.logout()
        response = self.client.post(reverse("product_create"), self.form_data())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(name="Qatiq").exists())

    def test_create_product(self):
        response = self.client.post(
            reverse("product_create"), self.form_data(name="  Qatiq ")
        )
        self.assertRedirects(response, reverse("product_list"))
        product = Product.objects.get(name="Qatiq")
        self.assertEqual(product.category, self.dairy)
        self.assertEqual(str(product), "Qatiq, Sof Sut, 0.5 litre")

    def test_edit_product(self):
        url = reverse("product_update", args=[self.milk.pk])
        self.assertContains(self.client.get(url), "Sut 3.2%")
        data = self.form_data(name="Sut 2.5%")
        del data["is_active"]
        self.assertRedirects(self.client.post(url, data), reverse("product_list"))
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.name, "Sut 2.5%")
        self.assertFalse(self.milk.is_active)

    def test_invalid_data_is_rejected_with_messages(self):
        response = self.client.post(
            reverse("product_create"), self.form_data(name="", unit_size="0")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertIn("unit_size", response.context["form"].errors)

    def test_duplicate_product_is_rejected(self):
        self.client.post(reverse("product_create"), self.form_data())
        response = self.client.post(reverse("product_create"), self.form_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.filter(name="Qatiq").count(), 1)


class PriceEntryTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        self.store = Store.objects.create(name="Baraka", city=city)
        self.other_store = Store.objects.create(name="Arzon", city=city)
        self.url = reverse("price_entry")

    def post(self, **fields):
        return self.client.post(self.url, {"store": self.store.pk, **fields})

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.post(**{f"price_{self.milk.pk}": "12000"})
        self.assertEqual(Price.objects.count(), 0)

    def test_page_lists_active_products_with_current_price(self):
        Price.objects.create(product=self.milk, store=self.store, amount=11000)
        Price.objects.create(product=self.milk, store=self.store, amount=12000)
        Price.objects.create(product=self.milk, store=self.other_store, amount=99000)
        self.sugar.is_active = False
        self.sugar.save()
        response = self.client.get(self.url, {"store": self.store.pk})
        rows = response.context["rows"]
        self.assertEqual([row["product"] for row in rows], [self.milk])
        self.assertEqual(rows[0]["current"].amount, 12000)

    def test_saves_only_filled_rows(self):
        response = self.post(
            **{f"price_{self.milk.pk}": "12 500", f"price_{self.sugar.pk}": ""}
        )
        self.assertRedirects(response, f"{self.url}?store={self.store.pk}")
        price = Price.objects.get()
        self.assertEqual((price.product, price.store), (self.milk, self.store))
        self.assertEqual(price.amount, 12500)
        self.assertFalse(price.is_promo)

    def test_unchanged_price_is_not_saved_again(self):
        self.post(**{f"price_{self.milk.pk}": "12500"})
        self.post(**{f"price_{self.milk.pk}": "12500,00"})
        self.assertEqual(Price.objects.count(), 1)
        self.post(**{f"price_{self.milk.pk}": "13000"})
        self.assertEqual(Price.objects.count(), 2)

    def test_promo_price_with_end_date(self):
        self.post(
            **{
                f"price_{self.milk.pk}": "9900",
                f"promo_{self.milk.pk}": "on",
                f"price_{self.sugar.pk}": "12000",
                "promo_ends": "2030-01-15",
            }
        )
        promo = Price.objects.get(product=self.milk)
        regular = Price.objects.get(product=self.sugar)
        self.assertTrue(promo.is_promo)
        self.assertEqual(str(promo.promo_ends), "2030-01-15")
        self.assertFalse(regular.is_promo)
        self.assertIsNone(regular.promo_ends)

    def test_one_bad_value_saves_nothing(self):
        for bad in ["abc", "0", "-5", "NaN", "1e99"]:
            with self.subTest(bad=bad):
                response = self.post(
                    **{f"price_{self.milk.pk}": bad, f"price_{self.sugar.pk}": "12000"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Enter a price greater than zero.")
                # The typed values stay in the form.
                self.assertContains(response, 'value="12000"')
                self.assertEqual(Price.objects.count(), 0)

    def test_bad_promo_date_saves_nothing(self):
        response = self.post(
            **{f"price_{self.milk.pk}": "12000", "promo_ends": "not-a-date"}
        )
        self.assertContains(response, "Enter a valid date.")
        self.assertEqual(Price.objects.count(), 0)
