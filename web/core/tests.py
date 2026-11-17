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
    def test_index(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)

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
