from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.models import Category, Price, Product
from locations.models import City, Store
from posts.models import Post

PROJECT_APPS = {"locations", "catalog", "baskets", "posts"}


class AdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "admin", "admin@example.com", "unused-in-tests"
        )
        self.client.force_login(self.user)

    def test_every_admin_page_opens(self):
        """Changelist and add page of every model of the project's apps."""
        models = [m for m in admin.site._registry if m._meta.app_label in PROJECT_APPS]
        self.assertEqual(len(models), 8)
        for model in models:
            opts = model._meta
            base = f"/admin/{opts.app_label}/{opts.model_name}/"
            for url in (base, base + "add/"):
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_prices_are_add_only_and_record_the_author(self):
        city = City.objects.create(name="Andijon", slug="andijon")
        store = Store.objects.create(name="Makro", city=city)
        product = Product.objects.create(
            name="Sut", category=Category.objects.create(name="Sut", slug="sut")
        )
        self.client.post("/admin/catalog/price/add/", {
            "product": product.pk, "store": store.pk, "price": "9000",
            "regular_price": "", "promo_until": "", "observed_on": "2026-11-01",
        })
        price = Price.objects.get()
        self.assertEqual(price.created_by, self.user)
        response = self.client.post(
            f"/admin/catalog/price/{price.pk}/change/", {"price": "1"}
        )
        self.assertEqual(response.status_code, 403)
        price.refresh_from_db()
        self.assertEqual(price.price, 9000)

    def test_post_admin_records_the_author(self):
        self.client.post("/admin/posts/post/add/", {
            "title": "", "body": "Salom", "rubric": "lifehack", "language": "uz",
            "status": "draft", "extra_tags": "", "comments_enabled": "on",
        })
        post = Post.objects.get()
        self.assertEqual(post.created_by, self.user)
        self.assertEqual(post.hashtags, "#Layfxak")
