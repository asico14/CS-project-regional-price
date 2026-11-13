from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


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
