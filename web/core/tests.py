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
        self.assertTemplateUsed(response, "403.html")

    def test_staff_can_log_in_and_out(self):
        response = self.client.post(
            reverse("login"), {"username": "staff", "password": "pw", "next": "/"}
        )
        self.assertRedirects(response, "/")
        self.assertContains(self.client.get("/"), 'action="/logout/"')
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


class LanguageTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user("staff", password="pw", is_staff=True)
        self.client.force_login(staff)

    def test_uzbek_is_the_default_language(self):
        response = self.client.get("/")
        self.assertContains(response, '<html lang="uz">')
        self.assertContains(response, "Mahsulotlar")
        self.assertContains(response, "Chiqish")

    def test_switching_to_russian_and_back(self):
        response = self.client.post(
            reverse("set_language"), {"language": "ru", "next": "/"}
        )
        self.assertRedirects(response, "/")
        response = self.client.get("/")
        self.assertContains(response, '<html lang="ru">')
        self.assertContains(response, "Товары")
        self.client.post(reverse("set_language"), {"language": "uz", "next": "/"})
        self.assertContains(self.client.get("/"), "Mahsulotlar")

    def test_unknown_language_is_ignored(self):
        self.client.post(reverse("set_language"), {"language": "de", "next": "/"})
        self.assertContains(self.client.get("/"), '<html lang="uz">')

    def test_browser_language_is_respected(self):
        response = self.client.get("/", headers={"accept-language": "ru"})
        self.assertContains(response, "Товары")

    def test_login_page_is_translated(self):
        self.client.logout()
        self.assertContains(self.client.get(reverse("login")), "Kirish")
