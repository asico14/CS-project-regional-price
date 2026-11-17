from django.test import TestCase
from django.urls import reverse


class SmokeTests(TestCase):
    def test_index(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)

    def test_health(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})


class SeedDemoTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        from io import StringIO

        from django.core.management import call_command

        from catalog.models import Product
        from locations.models import City, Store

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
