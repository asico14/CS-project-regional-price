from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Price, Product
from locations.models import City, Store


class SmokeTests(TestCase):
    def test_health(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})


class AdminTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser("admin", password="pw")
        self.client.force_login(admin)
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        store = Store.objects.create(name="Baraka", city=city)
        category = Category.objects.create(name="Sut", slug="sut")
        product = Product.objects.create(name="Sut", category=category)
        self.price = Price.objects.create(product=product, store=store, amount=12000)

    def test_all_models_are_registered(self):
        for app, model in [
            ("locations", "city"),
            ("locations", "district"),
            ("locations", "store"),
            ("catalog", "category"),
            ("catalog", "product"),
            ("catalog", "price"),
        ]:
            with self.subTest(model=model):
                url = reverse(f"admin:{app}_{model}_changelist")
                self.assertEqual(self.client.get(url).status_code, 200)
                add_url = reverse(f"admin:{app}_{model}_add")
                self.assertEqual(self.client.get(add_url).status_code, 200)

    def test_price_is_read_only_in_admin(self):
        change_url = reverse("admin:catalog_price_change", args=[self.price.pk])
        response = self.client.post(change_url, {"amount": "1"})
        self.assertEqual(response.status_code, 403)
        delete_url = reverse("admin:catalog_price_delete", args=[self.price.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)
        self.price.refresh_from_db()
        self.assertEqual(self.price.amount, 12000)


class AuthTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.staff = users.create_user("staff", password="pw", is_staff=True)
        self.reader = users.create_user("reader", password="pw")

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse("index"))
        self.assertRedirects(response, "/login/?next=/")

    def test_non_staff_user_gets_403(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "No access", status_code=403)

    def test_staff_can_log_in_and_out(self):
        response = self.client.post(
            reverse("login"), {"username": "staff", "password": "pw", "next": "/"}
        )
        self.assertRedirects(response, "/")
        self.assertContains(self.client.get("/"), "Log out")
        # Logging out must be a POST request.
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("logout")), "/login/")
        self.assertRedirects(self.client.get("/"), "/login/?next=/")

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("login"), {"username": "staff", "password": "nope"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(self.client.get("/"), "/login/?next=/")

    def test_health_stays_public(self):
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)
