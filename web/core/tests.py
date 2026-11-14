import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import SuspiciousFileOperation
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.views.static import serve

from baskets.models import Basket
from catalog.models import Category, Price, Product
from locations.models import City, Store
from posts.models import Post

from .access import staff_required
from .dashboard import dashboard_data


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
        self.assertContains(response, "Boshqaruv paneli")
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


class DashboardTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user("staff", password="pw", is_staff=True)
        self.client.force_login(staff)
        self.now = timezone.now()

    def post(self, title, status="draft", hours=None, **extra):
        when = self.now + timedelta(hours=hours) if hours is not None else None
        return Post.objects.create(
            rubric="price", title=title, text="x", status=status, scheduled_at=when, **extra
        )

    def test_empty_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["counts"].values()), {0})
        self.assertEqual(response.context["upcoming"], [])
        self.assertEqual(response.context["failures"], [])

    def test_counts(self):
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        store = Store.objects.create(name="Baraka", city=city)
        Store.objects.create(name="Yopiq", city=city, is_active=False)
        category = Category.objects.create(name="Sut", slug="sut")
        milk = Product.objects.create(name="Sut", category=category)
        bread = Product.objects.create(name="Non", category=category)
        Product.objects.create(name="Eski", category=category, is_active=False)
        yesterday = self.now - timedelta(days=1)
        today = timezone.localdate()
        Price.objects.create(product=milk, store=store, amount=1, recorded_at=yesterday)
        # A running promotion, and one that was replaced by a regular price.
        Price.objects.create(product=milk, store=store, amount=1, is_promo=True)
        Price.objects.create(
            product=bread, store=store, amount=1, is_promo=True, recorded_at=yesterday
        )
        Price.objects.create(product=bread, store=store, amount=2)
        # ...and one that has ended.
        eggs = Product.objects.create(name="Tuxum", category=category)
        Price.objects.create(
            product=eggs,
            store=store,
            amount=1,
            is_promo=True,
            promo_ends=today - timedelta(days=1),
            recorded_at=yesterday,
        )
        Basket.objects.create(name="Savat")
        self.post("a")
        self.post("b", "scheduled", hours=1)
        self.post("c", "published")
        self.post("d", "failed")
        self.post("e", "failed")
        data = dashboard_data()
        self.assertEqual(
            data["counts"],
            {"products": 3, "stores": 1, "prices_today": 2, "promotions": 1, "baskets": 1},
        )
        self.assertEqual(
            {status: data["posts"][status] for status in ["draft", "scheduled", "published", "failed"]},
            {"draft": 1, "scheduled": 1, "published": 1, "failed": 2},
        )

    def test_upcoming_posts_are_the_next_five_in_time_order(self):
        for hours in [30, 2, 50, 8, 1, 20, 4]:
            self.post(f"in {hours}", "scheduled", hours=hours)
        self.post("late", "scheduled", hours=-3)
        self.post("draft with time", "draft", hours=1)
        upcoming = dashboard_data()["upcoming"]
        self.assertEqual(
            [post.title for post in upcoming], ["late", "in 1", "in 2", "in 4", "in 8"]
        )
        self.assertEqual([post.overdue for post in upcoming], [True] + [False] * 4)
        self.assertContains(self.client.get("/"), "kechikkan", count=1)

    def test_recent_failures_show_the_error(self):
        self.post("ok", "published")
        self.post("Xato post", "failed", error_message="Chat not found")
        response = self.client.get("/")
        self.assertEqual([post.title for post in response.context["failures"]], ["Xato post"])
        self.assertContains(response, "Chat not found")


class MediaAccessTests(TestCase):
    """Uploaded post photos are served by Django, to staff only."""

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get("/media/posts/photo.png")
        self.assertRedirects(response, "/login/?next=/media/posts/photo.png")

    def test_staff_can_open_a_photo_but_not_escape_the_folder(self):
        staff = get_user_model().objects.create_user("s", password="pw", is_staff=True)
        self.client.force_login(staff)
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "photo.png").write_bytes(b"image bytes")
            request = self.client.get("/").wsgi_request
            view = staff_required(serve)
            response = view(request, path="photo.png", document_root=folder)
            self.assertEqual(response.status_code, 200)
            # Django answers a path that leaves the folder with "400 Bad Request".
            with self.assertRaises(SuspiciousFileOperation):
                view(request, path="../manage.py", document_root=folder)
        self.assertEqual(self.client.get("/media/missing.png").status_code, 404)
