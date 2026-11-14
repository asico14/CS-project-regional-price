from datetime import date

from django.test import SimpleTestCase

from .generators import format_date, format_price, render_generator


class FormatTests(SimpleTestCase):
    def test_format_price(self):
        self.assertEqual(format_price(12500), "12 500")
        self.assertEqual(format_price(1234567.4), "1 234 567")
        self.assertEqual(format_price(900), "900")

    def test_format_date(self):
        self.assertEqual(format_date(date(2026, 11, 5)), "05.11.2026")


class GeneratorTemplateTests(SimpleTestCase):
    """Every template renders in Uzbek and in Russian from one source."""

    promotion = {
        "city": "Qo'qon",
        "items": [
            {
                "product": "Shakar, 1 kg",
                "price": "11 000",
                "old_price": "12 500",
                "percent": 12,
                "store": "Baraka Market",
                "ends": "20.11.2026",
            },
            {"product": "Sut", "price": "9 000", "store": "Arzon Savdo"},
        ],
        "more": 3,
    }

    def test_promotion_in_uzbek(self):
        title, text = render_generator("promotion", "uz", self.promotion)
        self.assertEqual(title, "Qo'qon shahridagi aksiyalar")
        self.assertEqual(
            text,
            "🔥 Shakar, 1 kg — 11 000 so'm (avval 12 500, −12%)\n"
            "📍 Baraka Market · 20.11.2026 gacha\n"
            "\n"
            "🔥 Sut — 9 000 so'm\n"
            "📍 Arzon Savdo\n"
            "\n"
            "…va yana 3 ta aksiya.\n"
            "\n"
            "Narxlar o'zgarishi mumkin — do'konda aniqlang.",
        )

    def test_promotion_in_russian_with_plural_forms(self):
        title, text = render_generator("promotion", "ru", self.promotion)
        self.assertEqual(title, "Акции в городе Qo'qon")
        self.assertIn("11 000 сум (было 12 500, −12%)", text)
        self.assertIn("до 20.11.2026", text)
        for count, phrase in [(1, "1 акция"), (3, "3 акции"), (5, "5 акций")]:
            _, text = render_generator("promotion", "ru", {**self.promotion, "more": count})
            self.assertIn(f"…и ещё {phrase}.", text)

    def test_promotion_without_city_or_extra(self):
        title, text = render_generator("promotion", "uz", {"items": [], "more": 0})
        self.assertEqual(title, "Vodiydagi aksiyalar")
        self.assertNotIn("yana", text)

    def test_price(self):
        context = {
            "product": "Shakar, 1 kg",
            "city": "Andijon",
            "items": [
                {"store": "Arzon Savdo", "price": "11 000", "cheapest": True, "promo": True},
                {"store": "Baraka Market", "price": "12 500"},
            ],
            "difference": "1 500",
            "date": "14.11.2026",
        }
        title, text = render_generator("price", "uz", context)
        self.assertEqual(title, "Shakar, 1 kg: Andijon shahridagi narxlar")
        self.assertEqual(
            text,
            "✅ Arzon Savdo — 11 000 so'm (aksiya)\n"
            "▫️ Baraka Market — 12 500 so'm\n"
            "\n"
            "Eng arzon va eng qimmat narx orasidagi farq: 1 500 so'm.\n"
            "\n"
            "Narxlar 14.11.2026 kuni tekshirilgan.",
        )
        title, text = render_generator("price", "ru", context)
        self.assertEqual(title, "Shakar, 1 kg: цены в городе Andijon")
        self.assertIn("✅ Arzon Savdo — 11 000 сум (акция)", text)

    def test_basket(self):
        context = {
            "basket": "Haftalik savat",
            "city": "Namangan",
            "contents": "2 × Sut, 3 × Non",
            "items": [
                {"place": 1, "store": "Arzon Savdo", "total": "37 500"},
                {"place": 2, "store": "Baraka Market", "total": "38 000", "extra": "500"},
            ],
            "saving": "500",
            "skipped": 2,
            "date": "14.11.2026",
        }
        title, text = render_generator("basket", "uz", context)
        self.assertEqual(title, "“Haftalik savat” savati: Namangan shahrida qayerda arzon?")
        self.assertIn("Savatda: 2 × Sut, 3 × Non", text)
        self.assertIn("1. Arzon Savdo — 37 500 so'm\n2. Baraka Market — 38 000 so'm (+500)", text)
        self.assertIn("500 so'm tejaysiz", text)
        self.assertIn("2 ta do'kon ro'yxatga kirmadi", text)
        title, text = render_generator("basket", "ru", context)
        self.assertEqual(title, "Корзина «Haftalik savat»: где дешевле в городе Namangan?")
        self.assertIn("2 магазина не вошли в список", text)

    def test_new_store(self):
        context = {
            "store": "Baraka Market",
            "city": "Marg'ilon",
            "address": "Markaz, 1-uy",
            "products": 21,
            "cheapest": "Shakar, Sut",
        }
        title, text = render_generator("new_store", "uz", context)
        self.assertEqual(title, "Marg'ilon shahrida yangi do'kon: Baraka Market")
        self.assertIn("📍 Manzil: Markaz, 1-uy", text)
        self.assertIn("21 ta mahsulot narxi allaqachon ma'lum.", text)
        self.assertIn("Shahar bo'yicha eng arzoni shu yerda: Shakar, Sut", text)
        title, text = render_generator("new_store", "ru", context)
        self.assertIn("Уже известна цена 21 товара.", text)
        _, text = render_generator("new_store", "uz", {"store": "X", "city": "Y"})
        self.assertNotIn("Manzil", text)

    def test_values_are_not_html_escaped(self):
        # Posts are stored as plain text; escaping happens when publishing.
        title, _ = render_generator("new_store", "uz", {"store": "A & B", "city": "Qo'qon"})
        self.assertEqual(title, "Qo'qon shahrida yangi do'kon: A & B")

    def test_no_leftover_english_or_empty_line_runs(self):
        for name, context in [("promotion", self.promotion)]:
            for language in ["uz", "ru"]:
                title, text = render_generator(name, language, context)
                self.assertNotIn("\n\n\n", text)
                self.assertNotIn("Promotions", title)
