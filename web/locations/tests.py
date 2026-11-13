from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from .models import City, District, Store


class LocationModelTests(TestCase):
    def setUp(self):
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.fergana = City.objects.create(name="Farg'ona", slug="fargona")
        self.center = District.objects.create(city=self.kokand, name="Markaz")

    def test_str(self):
        store = Store.objects.create(name="Korzinka", city=self.kokand)
        self.assertEqual(str(self.kokand), "Qo'qon")
        self.assertEqual(str(self.center), "Markaz (Qo'qon)")
        self.assertEqual(str(store), "Korzinka (Qo'qon)")

    def test_district_name_unique_inside_city_only(self):
        District.objects.create(city=self.fergana, name="Markaz")
        with self.assertRaises(IntegrityError):
            District.objects.create(city=self.kokand, name="Markaz")

    def test_store_district_must_belong_to_store_city(self):
        store = Store(name="Makro", city=self.fergana, district=self.center)
        with self.assertRaises(ValidationError):
            store.full_clean()
        store.city = self.kokand
        store.full_clean()

    def test_city_with_stores_cannot_be_deleted(self):
        Store.objects.create(name="Korzinka", city=self.kokand)
        with self.assertRaises(ProtectedError):
            self.kokand.delete()

    def test_deleting_district_keeps_store(self):
        store = Store.objects.create(
            name="Korzinka", city=self.kokand, district=self.center
        )
        self.center.delete()
        store.refresh_from_db()
        self.assertIsNone(store.district)
