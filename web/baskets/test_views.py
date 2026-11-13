from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Basket
from .tests import BasketTestCase


class BasketViewTests(BasketTestCase):
    def setUp(self):
        super().setUp()
        staff = get_user_model().objects.create_user(
            "staff", password="pw", is_staff=True
        )
        self.client.force_login(staff)

    def formset_data(self, rows, initial=0, **basket):
        data = {
            "name": "Oylik savat",
            "description": "",
            "items-TOTAL_FORMS": len(rows),
            "items-INITIAL_FORMS": initial,
            **basket,
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"items-{index}-{key}"] = value
        return data

    def test_pages_require_staff(self):
        self.client.logout()
        for url in [
            reverse("basket_list"),
            reverse("basket_create"),
            reverse("basket_detail", args=[self.basket.pk]),
            reverse("basket_update", args=[self.basket.pk]),
        ]:
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_list_shows_product_count(self):
        response = self.client.get(reverse("basket_list"))
        self.assertEqual(response.context["baskets"][0].item_count, 2)

    def test_create_basket_with_products(self):
        data = self.formset_data(
            [
                {"product": self.milk.pk, "quantity": "2"},
                {"product": self.sugar.pk, "quantity": "1.5"},
                {"product": "", "quantity": "1"},
            ]
        )
        response = self.client.post(reverse("basket_create"), data)
        basket = Basket.objects.get(name="Oylik savat")
        self.assertRedirects(response, reverse("basket_detail", args=[basket.pk]))
        self.assertEqual(basket.items.count(), 2)
        self.assertEqual(str(basket.items.get(product=self.sugar).quantity), "1.500")

    def test_edit_basket_changes_and_removes_products(self):
        milk_item = self.basket.items.get(product=self.milk)
        bread_item = self.basket.items.get(product=self.bread)
        data = self.formset_data(
            [
                {"id": milk_item.pk, "product": self.milk.pk, "quantity": "5"},
                {
                    "id": bread_item.pk,
                    "product": self.bread.pk,
                    "quantity": "3",
                    "DELETE": "on",
                },
            ],
            initial=2,
            name="Haftalik savat",
        )
        response = self.client.post(
            reverse("basket_update", args=[self.basket.pk]), data
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            [(item.product, int(item.quantity)) for item in self.basket.items.all()],
            [(self.milk, 5)],
        )

    def test_invalid_rows_save_nothing(self):
        for rows in (
            [{"product": self.milk.pk, "quantity": "0"}],
            [
                {"product": self.milk.pk, "quantity": "1"},
                {"product": self.milk.pk, "quantity": "2"},
            ],
        ):
            with self.subTest(rows=rows):
                response = self.client.post(
                    reverse("basket_create"), self.formset_data(rows)
                )
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Basket.objects.filter(name="Oylik savat").exists())

    def test_comparison_page_ranks_stores(self):
        self.fill(self.baraka, milk=13000, bread=4000)
        self.fill(self.arzon, milk=12000, bread=4500)
        self.price(self.dehqon, self.milk, 11000)
        response = self.client.get(reverse("basket_detail", args=[self.basket.pk]))
        results = response.context["results"]
        self.assertEqual(
            [result.store.name for result in results], ["Arzon", "Baraka", "Dehqon"]
        )
        self.assertContains(response, 'class="cheapest"', count=1)
        self.assertContains(response, "Partial total")
        filtered = self.client.get(
            reverse("basket_detail", args=[self.basket.pk]), {"city": self.fergana.pk}
        )
        self.assertEqual(len(filtered.context["results"]), 1)
        self.assertNotContains(filtered, 'class="cheapest"')

    def test_comparison_page_without_prices(self):
        response = self.client.get(reverse("basket_detail", args=[self.basket.pk]))
        self.assertContains(response, "has prices for the products of this basket")
