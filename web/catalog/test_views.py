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
