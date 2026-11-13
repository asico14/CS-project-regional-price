from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import City, District, Store


class StoreViewTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user(
            "staff", password="pw", is_staff=True
        )
        self.client.force_login(staff)
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.fergana = City.objects.create(name="Farg'ona", slug="fargona")
        self.center = District.objects.create(city=self.kokand, name="Markaz")
        self.baraka = Store.objects.create(name="Baraka", city=self.kokand)
        Store.objects.create(name="Arzon", city=self.fergana)

    def names(self, **params):
        response = self.client.get(reverse("store_list"), params)
        return [store.name for store in response.context["stores"]]

    def test_requires_staff(self):
        self.client.logout()
        response = self.client.get(reverse("store_list"))
        self.assertRedirects(response, "/login/?next=/stores/")

    def test_list_and_city_filter(self):
        self.assertEqual(self.names(), ["Arzon", "Baraka"])
        self.assertEqual(self.names(city=self.kokand.pk), ["Baraka"])
        self.assertEqual(len(self.names(city="abc")), 2)

    def test_create_store(self):
        response = self.client.post(
            reverse("store_create"),
            {
                "name": "Dehqon",
                "city": self.kokand.pk,
                "district": self.center.pk,
                "address": "Markaz, 5-uy",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("store_list"))
        self.assertEqual(Store.objects.get(name="Dehqon").district, self.center)

    def test_edit_store(self):
        url = reverse("store_update", args=[self.baraka.pk])
        response = self.client.post(
            url, {"name": "Baraka Plus", "city": self.kokand.pk, "district": ""}
        )
        self.assertRedirects(response, reverse("store_list"))
        self.baraka.refresh_from_db()
        self.assertEqual(self.baraka.name, "Baraka Plus")
        self.assertFalse(self.baraka.is_active)

    def test_district_from_another_city_is_rejected(self):
        response = self.client.post(
            reverse("store_create"),
            {"name": "Dehqon", "city": self.fergana.pk, "district": self.center.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("district", response.context["form"].errors)
        self.assertFalse(Store.objects.filter(name="Dehqon").exists())
