from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Price, Product
from core.testing import StaffTestCase
from locations.models import City, Store

from . import generators
from .models import Post


class GeneratorData(TestCase):
    def setUp(self):
        super().setUp()
        dairy = Category.objects.create(name="Sut mahsulotlari", slug="sut")
        self.milk = Product.objects.create(name="Sut", brand="Musaffo", category=dairy,
                                           unit="l", unit_size=Decimal("1"))
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.andijan = City.objects.create(name="Andijon", slug="andijon")
        self.korzinka = Store.objects.create(name="Korzinka", city=self.kokand,
                                             address="Turkiston 12")
        self.makro = Store.objects.create(name="Makro", city=self.kokand)
        self.havas = Store.objects.create(name="Havas", city=self.andijan)
        self.day = date(2026, 11, 10)

    def add(self, store, price, **extra):
        return Price.objects.create(product=self.milk, store=store, price=price,
                                    observed_on=extra.pop("day", self.day), **extra)


class PromotionGeneratorTests(GeneratorData):
    def test_promotion_post_uz_and_ru(self):
        until = timezone.localdate() + timedelta(days=3)
        promo = self.add(self.korzinka, 9000, regular_price=12000, promo_until=until)
        post = generators.promotion_post(promo, "uz")
        self.assertIsNone(post.pk)
        self.assertEqual((post.rubric, post.language, post.city),
                         ("promotion", "uz", self.kokand))
        self.assertEqual(post.title, "Aksiya: Korzinka")
        self.assertEqual(post.body.splitlines(), [
            "🔥 Sut, Musaffo, 1 litre",
            "🏪 Korzinka, Qo'qon",
            "💰 Hozir 9 000 so'm, avval 12 000 so'm edi (−25%)",
            f"⏳ {until:%d.%m.%Y} gacha amal qiladi",
            "📍 Manzil: Turkiston 12",
        ])
        ru = generators.promotion_post(promo, "ru")
        self.assertEqual(ru.title, "Акция: Korzinka")
        self.assertIn("Сейчас 9 000 сум вместо 12 000 сум", ru.body)

    def test_not_a_promotion(self):
        with self.assertRaises(ValueError):
            generators.promotion_post(self.add(self.korzinka, 9000))


class PricePostGeneratorTests(GeneratorData):
    def test_price_post_cheapest_first(self):
        self.add(self.korzinka, 10000)
        self.add(self.makro, 9000, day=date(2026, 11, 12))
        self.add(self.havas, 11000)
        post = generators.price_post(self.milk, "uz")
        self.assertEqual(post.title, "Narxlar: Sut")
        self.assertIsNone(post.city)
        lines = post.body.splitlines()
        self.assertEqual(lines[0], "📊 Farg'ona vodiysida Sut, Musaffo, 1 litre narxlari:")
        self.assertEqual(lines[1], "")  # blank line before the list
        self.assertEqual(lines[2:5], [
            "1. Makro (Qo'qon) — 9 000 so'm ✅",
            "2. Korzinka (Qo'qon) — 10 000 so'm",
            "3. Havas (Andijon) — 11 000 so'm",
        ])
        self.assertIn("farq 2 000 so'm (22%)", post.body)
        self.assertEqual(lines[-1], "Narxlar 12.11.2026 holatiga.")

    def test_price_post_for_one_city_in_russian(self):
        self.add(self.korzinka, 10000)
        self.add(self.havas, 1000)
        post = generators.price_post(self.milk, "ru", city=self.kokand)
        self.assertEqual(post.city, self.kokand)
        self.assertIn("в городе Qo'qon", post.body)
        self.assertIn("1. Korzinka — 10 000 сум ✅", post.body)
        self.assertNotIn("Havas", post.body)
        self.assertNotIn("Разница", post.body)  # one store: nothing to compare

    def test_no_prices(self):
        with self.assertRaises(ValueError):
            generators.price_post(self.milk)


class GeneratePageTests(GeneratorData, StaffTestCase):
    def test_staff_only(self):
        self.assertStaffOnly(reverse("posts:post_generate"))

    def test_generate_promotion_draft(self):
        promo = self.add(self.korzinka, 9000, regular_price=12000)
        self.add(self.makro, 9000)  # not a promotion: not offered
        response = self.client.get(reverse("posts:post_generate"))
        form = response.context["forms"][0]
        self.assertEqual(list(form.fields["price"].queryset), [promo])
        response = self.client.post(reverse("posts:post_generate"), {
            "kind": "promotion", "promotion-price": promo.pk,
            "promotion-language": "ru",
        })
        post = Post.objects.get()
        self.assertRedirects(response, reverse("posts:post_edit", args=[post.pk]))
        self.assertEqual((post.status, post.language, post.created_by),
                         ("draft", "ru", self.user))
        self.assertEqual(post.hashtags, "#Акция #Qoqon")

    def test_price_generator_prefill_and_error(self):
        response = self.client.get(reverse("posts:post_generate"),
                                   {"price-product": self.milk.pk})
        self.assertEqual(response.context["forms"][1].initial,
                         {"product": str(self.milk.pk)})
        response = self.client.post(reverse("posts:post_generate"), {
            "kind": "price", "price-product": self.milk.pk, "price-language": "uz",
        })
        self.assertContains(response, "no prices for this product")
        self.assertFalse(Post.objects.exists())
