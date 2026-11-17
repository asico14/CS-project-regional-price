from io import StringIO

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views import View

from catalog.models import Price, Product
from locations.models import City, Store

from .permissions import StaffRequiredMixin, staff_required
from .testing import PASSWORD, make_user


class SmokeTests(TestCase):
    def test_index_needs_login(self):
        response = self.client.get(reverse("index"))
        self.assertRedirects(
            response, "/login/?next=/", fetch_redirect_response=False
        )

    def test_health(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})


class AuthTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        @staff_required
        def view(request):
            return HttpResponse("ok")

        class ClassView(StaffRequiredMixin, View):
            def get(self, request):
                return HttpResponse("ok")

        self.views = [view, ClassView.as_view()]

    def request(self, user=None):
        request = self.factory.get("/secret/")
        request.user = user or AnonymousUser()
        return request

    def test_anonymous_user_is_sent_to_login(self):
        for view in self.views:
            response = view(self.request())
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, "/login/?next=/secret/")

    def test_non_staff_user_is_forbidden(self):
        user = make_user(staff=False)
        for view in self.views:
            with self.assertRaises(PermissionDenied):
                view(self.request(user))

    def test_staff_user_gets_the_page(self):
        user = make_user()
        for view in self.views:
            self.assertEqual(view(self.request(user)).content, b"ok")

    def test_login_and_logout(self):
        make_user()
        response = self.client.post(
            reverse("login"), {"username": "editor", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("index"), fetch_redirect_response=False)
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class SeedDemoTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo", stdout=StringIO())
        counts = (City.objects.count(), Store.objects.count(), Product.objects.count())
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(
            counts,
            (City.objects.count(), Store.objects.count(), Product.objects.count()),
        )
        self.assertEqual(counts[0], 5)
        for store in Store.objects.select_related("district"):
            self.assertEqual(store.district.city_id, store.city_id)

    def test_seed_demo_generates_prices_once(self):
        call_command("seed_demo", "--days=20", stdout=StringIO())
        total = Price.objects.count()
        self.assertGreater(total, 100)
        promos = Price.objects.filter(regular_price__isnull=False)
        self.assertTrue(promos.exists())
        for promo in promos:
            self.assertLess(promo.price, promo.regular_price)
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(Price.objects.count(), total)
        call_command("seed_demo", "--days=5", "--reset-prices", stdout=StringIO())
        self.assertLess(Price.objects.count(), total)


class DashboardTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from catalog.models import Category
        from posts.models import Post

        self.client.force_login(make_user())
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        fresh = Store.objects.create(name="Fresh", city=city)
        Store.objects.create(name="Stale", city=city)
        product = Product.objects.create(
            name="Sut", category=Category.objects.create(name="Sut", slug="sut")
        )
        today = timezone.localdate()
        Price.objects.create(product=product, store=fresh, price=9000,
                             observed_on=today - timedelta(days=1))
        Price.objects.create(product=product, store=fresh, price=8000,
                             regular_price=9000, observed_on=today)
        now = timezone.now()
        Post.objects.create(body="soon", rubric="price", status="scheduled",
                            scheduled_at=now + timedelta(hours=2))
        Post.objects.create(body="broken", rubric="price", status="failed",
                            last_error="Chat not found")
        Post.objects.create(body="done", rubric="price", status="published",
                            scheduled_at=now, published_at=now)

    def test_dashboard(self):
        response = self.client.get(reverse("index"))
        counts = response.context["counts"]
        self.assertEqual(counts["products"], 1)
        self.assertEqual(counts["stores"], 2)
        self.assertEqual(counts["prices_today"], 1)
        self.assertEqual(counts["prices_week"], 2)
        self.assertEqual(counts["promotions"], 1)
        self.assertEqual((counts["scheduled"], counts["failed"],
                          counts["published_week"]), (1, 1, 1))
        self.assertEqual([p.body for p in response.context["upcoming"]], ["soon"])
        self.assertContains(response, "Chat not found")
        self.assertEqual([s.name for s in response.context["stale_stores"]], ["Stale"])

    def test_staff_only(self):
        from .testing import StaffTestCase

        StaffTestCase.assertStaffOnly(self, reverse("index"))
