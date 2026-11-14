from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from baskets.models import Basket, BasketItem
from catalog.models import Category, Price, Product
from locations.models import City, Store

from .formatting import TEXT_LIMIT, compose_text, telegram_length
from .generators import (
    NothingToPost,
    generate_basket_post,
    generate_price_post,
    generate_promotion_post,
    generate_store_post,
)
from .hashtags import hashtags_for_post
from .models import Post


class GeneratorTestCase(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Bakaleya", slug="bakaleya")
        self.sugar = Product.objects.create(name="Shakar", category=self.category, unit="kg")
        self.milk = Product.objects.create(name="Sut", category=self.category, unit="l")
        self.kokand = City.objects.create(name="Qo'qon", slug="qoqon")
        self.andijan = City.objects.create(name="Andijon", slug="andijon")
        self.baraka = Store.objects.create(name="Baraka", city=self.kokand)
        self.arzon = Store.objects.create(name="Arzon", city=self.kokand)
        self.dehqon = Store.objects.create(name="Dehqon", city=self.andijan)
        self.today = timezone.localdate()
        self.staff = get_user_model().objects.create_user(
            "staff", password="pw", is_staff=True
        )

    def price(self, product, store, amount, days_ago=0, **extra):
        return Price.objects.create(
            product=product,
            store=store,
            amount=amount,
            recorded_at=timezone.now() - timedelta(days=days_ago),
            **extra,
        )

    def promo(self, product, store, amount, ends_in=3, **extra):
        ends = self.today + timedelta(days=ends_in) if ends_in is not None else None
        return self.price(product, store, amount, is_promo=True, promo_ends=ends, **extra)


class PromotionPostTests(GeneratorTestCase):
    def test_lists_running_promotions_with_discount(self):
        self.price(self.sugar, self.baraka, 12500, days_ago=5)
        self.promo(self.sugar, self.baraka, 10000)
        self.promo(self.milk, self.arzon, 9000, ends_in=None)
        post = generate_promotion_post(self.kokand, "uz", self.staff)
        self.assertEqual(post.title, "Qo'qon shahridagi aksiyalar")
        ends = (self.today + timedelta(days=3)).strftime("%d.%m.%Y")
        self.assertEqual(
            post.text,
            "🔥 Shakar, 1 kg — 10 000 so'm (avval 12 500, −20%)\n"
            f"📍 Baraka · {ends} gacha\n"
            "\n"
            "🔥 Sut, 1 litre — 9 000 so'm\n"
            "📍 Arzon\n"
            "\n"
            "Narxlar o'zgarishi mumkin — do'konda aniqlang.",
        )
        self.assertEqual(
            (post.rubric, post.status, post.language, post.city, post.created_by),
            ("promotion", "draft", "uz", self.kokand, self.staff),
        )
        self.assertIsNone(post.pk)
        self.assertEqual(hashtags_for_post(post), ["#aksiya", "#Qoqon"])

    def test_whole_valley_post_names_the_city_of_each_store(self):
        self.promo(self.sugar, self.baraka, 10000)
        self.promo(self.sugar, self.dehqon, 9500)
        post = generate_promotion_post(language="ru")
        self.assertEqual(post.title, "Акции в долине")
        self.assertIn("📍 Baraka (Qo'qon)", post.text)
        self.assertIn("📍 Dehqon (Andijon)", post.text)
        self.assertIsNone(post.city)

    def test_only_promotions_that_are_running_now(self):
        self.promo(self.sugar, self.baraka, 10000, ends_in=-1)  # ended
        self.promo(self.milk, self.baraka, 9000, days_ago=2)  # replaced
        self.price(self.milk, self.baraka, 12000)
        self.promo(self.sugar, self.dehqon, 9500)  # another city
        self.arzon.is_active = False
        self.arzon.save()
        self.promo(self.sugar, self.arzon, 9000)  # closed store
        with self.assertRaises(NothingToPost):
            generate_promotion_post(self.kokand)
        self.assertIn("Dehqon", generate_promotion_post().text)

    def test_promo_that_is_not_cheaper_shows_no_discount(self):
        self.price(self.sugar, self.baraka, 10000, days_ago=5)
        self.promo(self.sugar, self.baraka, 10000)
        text = generate_promotion_post(self.kokand).text
        self.assertNotIn("avval", text)

    def test_biggest_discounts_first_and_rest_is_counted(self):
        for number in range(14):
            product = Product.objects.create(name=f"Mahsulot {number:02}", category=self.category)
            self.price(product, self.baraka, 10000, days_ago=5)
            self.promo(product, self.baraka, 10000 - (number + 1) * 100)
        text = generate_promotion_post(self.kokand).text
        self.assertEqual(text.count("🔥"), 10)
        self.assertLess(text.index("Mahsulot 13"), text.index("Mahsulot 04"))
        self.assertNotIn("Mahsulot 03", text)
        self.assertIn("…va yana 4 ta aksiya.", text)

    def test_long_post_is_cut_to_the_telegram_limit(self):
        for number in range(10):
            product = Product.objects.create(
                name=f"{number} " + "juda uzun nom " * 25, category=self.category
            )
            store = Store.objects.create(name=f"{number} " + "do'kon " * 40, city=self.kokand)
            self.promo(product, store, 9000)
        post = generate_promotion_post(self.kokand)
        shown = post.text.count("🔥")
        self.assertLess(shown, 10)
        self.assertIn(f"…va yana {10 - shown} ta aksiya.", post.text)
        length = telegram_length(compose_text(post.title, post.text, hashtags_for_post(post)))
        self.assertLessEqual(length, TEXT_LIMIT)


class PricePostTests(GeneratorTestCase):
    def test_compares_stores_and_marks_cheapest(self):
        self.price(self.sugar, self.baraka, 12500)
        self.promo(self.sugar, self.arzon, 11000)
        self.price(self.sugar, self.dehqon, 9000)
        post = generate_price_post(self.sugar, self.kokand, "uz", self.staff)
        self.assertEqual(post.title, "Shakar, 1 kg: Qo'qon shahridagi narxlar")
        self.assertEqual(
            post.text,
            "✅ Arzon — 11 000 so'm (aksiya)\n"
            "▫️ Baraka — 12 500 so'm\n"
            "\n"
            "Eng arzon va eng qimmat narx orasidagi farq: 1 500 so'm.\n"
            "\n"
            f"Narxlar {self.today.strftime('%d.%m.%Y')} kuni tekshirilgan.",
        )
        self.assertEqual((post.rubric, post.city), ("price", self.kokand))

    def test_whole_valley_and_russian(self):
        self.price(self.sugar, self.baraka, 12500)
        self.price(self.sugar, self.dehqon, 9000)
        post = generate_price_post(self.sugar, language="ru")
        self.assertEqual(post.title, "Shakar, 1 kg: цены в долине")
        self.assertIn("✅ Dehqon (Andijon) — 9 000 сум", post.text)

    def test_single_store_or_equal_prices_have_no_difference_line(self):
        self.price(self.sugar, self.baraka, 12500)
        self.assertNotIn("farq", generate_price_post(self.sugar, self.kokand).text)
        self.price(self.sugar, self.arzon, 12500)
        text = generate_price_post(self.sugar, self.kokand).text
        self.assertNotIn("farq", text)
        self.assertEqual(text.count("✅"), 2)

    def test_ended_promotion_is_left_out(self):
        self.promo(self.sugar, self.baraka, 9000, ends_in=-1)
        with self.assertRaises(NothingToPost):
            generate_price_post(self.sugar, self.kokand)

    def test_no_prices(self):
        with self.assertRaises(NothingToPost):
            generate_price_post(self.milk)


class BasketPostTests(GeneratorTestCase):
    def setUp(self):
        super().setUp()
        self.basket = Basket.objects.create(name="Haftalik savat")
        BasketItem.objects.create(basket=self.basket, product=self.sugar, quantity=2)
        BasketItem.objects.create(basket=self.basket, product=self.milk, quantity="1.5")

    def fill(self, store, sugar, milk):
        self.price(self.sugar, store, sugar)
        self.price(self.milk, store, milk)

    def test_ranks_complete_stores(self):
        self.fill(self.baraka, sugar=12000, milk=10000)  # 24000 + 15000
        self.fill(self.arzon, sugar=11000, milk=10000)  # 22000 + 15000
        self.price(self.sugar, self.dehqon, 5000)
        post = generate_basket_post(self.basket, self.kokand, "uz", self.staff)
        self.assertEqual(
            post.title, "“Haftalik savat” savati: Qo'qon shahrida qayerda arzon?"
        )
        self.assertEqual(
            post.text,
            "Savatda: 2 × Shakar, 1.5 × Sut\n"
            "\n"
            "1. Arzon — 37 000 so'm\n"
            "2. Baraka — 39 000 so'm (+2 000)\n"
            "\n"
            "Eng arzon do'konda eng qimmatiga nisbatan 2 000 so'm tejaysiz.\n"
            "\n"
            f"Narxlar {self.today.strftime('%d.%m.%Y')} kuni tekshirilgan.",
        )
        self.assertEqual((post.rubric, post.city), ("comparison", self.kokand))
        self.assertEqual(hashtags_for_post(post), ["#taqqoslash", "#Qoqon"])

    def test_incomplete_stores_are_counted_but_not_ranked(self):
        self.fill(self.baraka, sugar=12000, milk=10000)
        self.price(self.sugar, self.arzon, 1000)
        self.price(self.sugar, self.dehqon, 1000)
        post = generate_basket_post(self.basket, language="ru")
        self.assertEqual(post.title, "Корзина «Haftalik savat»: где дешевле?")
        self.assertIn("1. Baraka (Qo'qon) — 39 000 сум", post.text)
        self.assertNotIn("Arzon", post.text)
        self.assertIn("2 магазина не вошли в список", post.text)
        # One ranked store: there is nothing to compare the saving with.
        self.assertNotIn("экономите", post.text)

    def test_no_complete_store(self):
        self.price(self.sugar, self.baraka, 12000)
        with self.assertRaises(NothingToPost):
            generate_basket_post(self.basket)
        with self.assertRaises(NothingToPost):
            generate_basket_post(Basket.objects.create(name="Bo'sh"))


class StorePostTests(GeneratorTestCase):
    def test_announces_store_with_address_and_cheapest_products(self):
        district = self.kokand.districts.create(name="Markaz")
        self.baraka.district = district
        self.baraka.address = "Navoiy ko'chasi, 5"
        self.baraka.save()
        self.price(self.sugar, self.baraka, 11000)
        self.price(self.sugar, self.arzon, 12000)
        self.price(self.milk, self.baraka, 10000)
        self.price(self.milk, self.arzon, 9000)
        post = generate_store_post(self.baraka, "uz", self.staff)
        self.assertEqual(post.title, "Qo'qon shahrida yangi do'kon: Baraka")
        self.assertEqual(
            post.text,
            "Endi Baraka do'konidagi narxlarni kuzatib boramiz.\n"
            "\n"
            "📍 Manzil: Markaz, Navoiy ko'chasi, 5\n"
            "\n"
            "2 ta mahsulot narxi allaqachon ma'lum.\n"
            "\n"
            "Shahar bo'yicha eng arzoni shu yerda: Shakar\n"
            "\n"
            "Qo'shishimiz kerak bo'lgan do'konni bilasizmi? Izohlarda yozing.",
        )
        self.assertEqual((post.rubric, post.city), ("store_news", self.kokand))

    def test_store_without_prices_or_address(self):
        post = generate_store_post(self.baraka, "ru")
        self.assertEqual(post.title, "Новый магазин в городе Qo'qon: Baraka")
        for word in ["Адрес", "известн", "дешевле"]:
            self.assertNotIn(word, post.text)

    def test_only_product_in_town_is_not_called_cheapest(self):
        self.price(self.sugar, self.baraka, 11000)
        self.price(self.sugar, self.dehqon, 20000)  # another city
        self.assertNotIn("eng arzoni", generate_store_post(self.baraka).text)

    def test_ended_promotion_of_a_rival_is_ignored(self):
        self.price(self.sugar, self.baraka, 11000)
        self.promo(self.sugar, self.arzon, 5000, ends_in=-1)
        self.assertNotIn("eng arzoni", generate_store_post(self.baraka).text)
        self.price(self.sugar, self.arzon, 12000)
        self.assertIn(
            "eng arzoni shu yerda: Shakar", generate_store_post(self.baraka).text
        )


class GenerateViewTests(GeneratorTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)
        self.url = reverse("post_generate")

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.post(self.url, {"kind": "promotion", "promotion-language": "uz"})
        self.assertFalse(Post.objects.exists())

    def test_page_shows_a_form_per_generator(self):
        response = self.client.get(self.url)
        kinds = [generator["kind"] for generator in response.context["generators"]]
        self.assertEqual(kinds, ["promotion", "price", "basket", "store"])

    def test_creates_draft_and_opens_it(self):
        self.promo(self.sugar, self.baraka, 10000)
        response = self.client.post(
            self.url,
            {"kind": "promotion", "promotion-city": self.kokand.pk, "promotion-language": "ru"},
        )
        post = Post.objects.get()
        self.assertRedirects(response, reverse("post_update", args=[post.pk]))
        self.assertEqual((post.status, post.language, post.created_by), ("draft", "ru", self.staff))

    def test_price_post_from_the_page(self):
        self.price(self.sugar, self.baraka, 12500)
        self.client.post(
            self.url, {"kind": "price", "price-product": self.sugar.pk, "price-language": "uz"}
        )
        self.assertEqual(Post.objects.get().rubric, "price")

    def test_basket_and_store_posts_from_the_page(self):
        basket = Basket.objects.create(name="Savat")
        BasketItem.objects.create(basket=basket, product=self.sugar)
        self.price(self.sugar, self.baraka, 12500)
        self.client.post(
            self.url,
            {"kind": "basket", "basket-basket": basket.pk, "basket-language": "uz"},
        )
        self.client.post(
            self.url,
            {"kind": "store", "store-store": self.baraka.pk, "store-language": "ru"},
        )
        self.assertEqual(
            sorted(Post.objects.values_list("rubric", "language")),
            [("comparison", "uz"), ("store_news", "ru")],
        )

    def test_nothing_to_post_is_explained(self):
        response = self.client.post(self.url, {"kind": "promotion", "promotion-language": "uz"})
        self.assertContains(response, "There are no running promotions.")
        self.assertFalse(Post.objects.exists())

    def test_invalid_form_and_unknown_kind(self):
        response = self.client.post(self.url, {"kind": "price", "price-language": "uz"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post(self.url, {"kind": "weather"}).status_code, 200)
        self.assertFalse(Post.objects.exists())
