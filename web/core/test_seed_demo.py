from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Category, Product
from locations.models import City, District, Store


def counts():
    models = (City, District, Store, Category, Product)
    return [model.objects.count() for model in models]


class SeedDemoTests(TestCase):
    def test_creates_demo_data(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(counts(), [5, 10, 15, 6, 22])
        for store in Store.objects.all():
            store.full_clean()

    def test_running_twice_creates_nothing_new(self):
        call_command("seed_demo", stdout=StringIO())
        first = counts()
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(counts(), first)
