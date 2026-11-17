from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.testing import StaffTestCase

from .hashtags import (
    MAX_HASHTAGS,
    MAX_TAG_LENGTH,
    build_hashtags,
    split_extra_tags,
    to_hashtag,
)
from .models import Post
from .telegram import compose_html, compose_plain, telegram_length


class PostModelTests(TestCase):
    def make(self, **extra):
        data = {"body": "Arzon sut!", "rubric": Post.Rubric.PROMOTION}
        data.update(extra)
        return Post.objects.create(**data)

    def test_defaults_and_str(self):
        post = self.make()
        self.assertEqual(post.status, Post.Status.DRAFT)
        self.assertEqual(post.language, "uz")
        self.assertEqual(str(post), "Arzon sut!")
        self.assertEqual(str(self.make(title="Aksiya")), "Aksiya")

    def test_scheduled_post_needs_a_time(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(status=Post.Status.SCHEDULED)
        with self.assertRaises(ValidationError):
            Post(body="x", rubric="price", status="scheduled").clean()

    def test_schedule_and_unschedule(self):
        post = self.make()
        when = timezone.now() + timedelta(hours=1)
        post.schedule(when)
        post.refresh_from_db()
        self.assertEqual((post.status, post.scheduled_at), ("scheduled", when))
        post.unschedule()
        self.assertEqual(post.status, "draft")

    def test_failed_post_can_be_rescheduled(self):
        post = self.make(status=Post.Status.FAILED, last_error="Network")
        post.schedule()
        self.assertEqual(post.status, "scheduled")
        self.assertEqual(post.last_error, "")
        self.assertIsNotNone(post.scheduled_at)

    def test_worker_states_are_locked_for_editors(self):
        for status in (Post.Status.PUBLISHING, Post.Status.PUBLISHED):
            post = self.make(status=status, scheduled_at=timezone.now())
            self.assertFalse(post.is_editable)
            with self.assertRaises(ValidationError):
                post.schedule()
            with self.assertRaises(ValidationError):
                post.unschedule()


class HashtagTests(TestCase):
    def test_to_hashtag(self):
        cases = {
            "Qo'qon": "#Qoqon",
            "Farg‘ona": "#Fargona",
            "Marg'ilon dehqon bozori": "#MargilonDehqonBozori",
            "#sut": "#Sut",
            "sut-mahsulotlari": "#SutMahsulotlari",
            "Coca-Cola 1.5": "#CocaCola15",
            "Новости магазинов": "#НовостиМагазинов",
            "black_friday": "#BlackFriday",
            "iPhone": "#IPhone",
            "2026": None,
            "  ": None,
            "!!!": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(to_hashtag(text), expected)

    def test_long_tags_are_cut(self):
        self.assertEqual(len(to_hashtag("a" * 100)), MAX_TAG_LENGTH + 1)

    def test_split_extra_tags(self):
        self.assertEqual(
            split_extra_tags("sut, #chegirma\nnon"), ["sut", "chegirma", "non"]
        )

    def test_build_hashtags_order_language_and_dedup(self):
        self.assertEqual(
            build_hashtags("promotion", "uz", "Qo'qon", "sut, #Aksiya, qoqon"),
            ["#Aksiya", "#Qoqon", "#Sut"],
        )
        self.assertEqual(build_hashtags("price", "ru"), ["#Цены"])
        # Unknown language falls back to Uzbek.
        self.assertEqual(build_hashtags("review", "en"), ["#Sharh"])

    def test_build_hashtags_limit(self):
        tags = build_hashtags("price", "uz", "Andijon", "a1, b2, c3, d4, e5")
        self.assertEqual(len(tags), MAX_HASHTAGS)
        self.assertEqual(tags[:2], ["#Narxlar", "#Andijon"])

    def test_post_stores_hashtags_on_save(self):
        from locations.models import City

        city = City.objects.create(name="Farg'ona", slug="fargona")
        post = Post.objects.create(body="x", rubric="lifehack", city=city,
                                   extra_tags="tejash")
        self.assertEqual(post.hashtags, "#Layfxak #Fargona #Tejash")
        post.language = "ru"
        post.save(update_fields=["language"])
        post.refresh_from_db()
        self.assertEqual(post.hashtags, "#Лайфхак #Fargona #Tejash")


class TelegramFormatTests(TestCase):
    def test_compose_escapes_and_bolds_title(self):
        html = compose_html("Narx <arzon>", "Sut & non", "#Narxlar")
        self.assertEqual(html, "<b>Narx &lt;arzon&gt;</b>\n\nSut &amp; non\n\n#Narxlar")
        self.assertEqual(compose_plain("", " Sut ", ""), "Sut")

    def test_length_counts_utf16_units(self):
        self.assertEqual(telegram_length("abc"), 3)
        self.assertEqual(telegram_length("Сут"), 3)
        self.assertEqual(telegram_length("🔥"), 2)


class PostPageTests(StaffTestCase):
    def data(self, **extra):
        data = {"rubric": "lifehack", "language": "uz", "title": "Maslahat",
                "body": "Bozorga ertalab boring.", "extra_tags": "",
                "scheduled_at": "", "action": "draft"}
        data.update(extra)
        return data

    def test_staff_only(self):
        self.assertStaffOnly(reverse("posts:post_list"))
        self.assertStaffOnly(reverse("posts:post_create"))

    def test_create_draft_then_schedule(self):
        response = self.client.post(reverse("posts:post_create"), self.data())
        post = Post.objects.get()
        self.assertRedirects(response, reverse("posts:post_edit", args=[post.pk]))
        self.assertEqual((post.status, post.created_by), ("draft", self.user))
        self.client.post(reverse("posts:post_edit", args=[post.pk]),
                         self.data(action="schedule"))
        post.refresh_from_db()
        self.assertEqual(post.status, "scheduled")
        self.assertIsNotNone(post.scheduled_at)  # empty time = as soon as possible
        self.client.post(reverse("posts:post_unschedule", args=[post.pk]))
        post.refresh_from_db()
        self.assertEqual(post.status, "draft")

    def test_text_limit(self):
        response = self.client.post(reverse("posts:post_create"),
                                    self.data(body="x" * 4100))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Telegram allows 4096", str(response.context["form"].errors))
        self.assertFalse(Post.objects.exists())

    def test_caption_limit_with_photo(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buffer, "JPEG")
        photo = SimpleUploadedFile("p.jpg", buffer.getvalue(), "image/jpeg")
        with self.settings(MEDIA_ROOT=self.tmp_media()):
            response = self.client.post(reverse("posts:post_create"),
                                        self.data(body="x" * 1100, image=photo))
            self.assertIn("Telegram allows 1024", str(response.context["form"].errors))
            photo.seek(0)
            response = self.client.post(reverse("posts:post_create"),
                                        self.data(body="x" * 900, image=photo))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Post.objects.get().image.name.startswith("posts/"))

    def tmp_media(self):
        import shutil
        import tempfile

        path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_published_post_cannot_be_edited(self):
        from django.utils import timezone

        post = Post.objects.create(body="x", rubric="price", status="published",
                                   scheduled_at=timezone.now())
        response = self.client.get(reverse("posts:post_edit", args=[post.pk]))
        self.assertRedirects(response, reverse("posts:post_list"))

    def test_preview_endpoint(self):
        from locations.models import City

        city = City.objects.create(name="Qo'qon", slug="qoqon")
        response = self.client.post(reverse("posts:post_preview"), {
            "title": "Aksiya", "body": "<b>sut</b>", "rubric": "promotion",
            "language": "uz", "city": city.pk, "has_image": "1",
        })
        data = response.json()
        self.assertEqual(data["hashtags"], "#Aksiya #Qoqon")
        self.assertIn("&lt;b&gt;sut&lt;/b&gt;", data["html"])
        self.assertEqual(data["limit"], 1024)
        self.assertEqual(data["length"], len("Aksiya\n\n<b>sut</b>\n\n#Aksiya #Qoqon"))

    def test_list_filters_by_status(self):
        Post.objects.create(body="a", rubric="price")
        Post.objects.create(body="b", rubric="price", status="failed")
        response = self.client.get(reverse("posts:post_list"), {"status": "failed"})
        self.assertEqual([p.body for p in response.context["post_list"]], ["b"])


class I18nTests(TestCase):
    def test_default_language_is_uzbek(self):
        from django.conf import settings

        self.assertEqual(settings.LANGUAGE_CODE, "uz")
        self.assertEqual([code for code, _ in settings.LANGUAGES], ["uz", "ru"])
        response = self.client.get(reverse("login"))
        self.assertContains(response, '<html lang="uz">')
        self.assertContains(response, "Kirish")

    def test_language_switch(self):
        self.client.post(reverse("set_language"), {"language": "ru", "next": "/login/"})
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Войти")

    def test_generator_templates_render_in_post_language(self):
        from .generators import render_text

        context = {"product": "Sut", "store": "Makro", "city": "Qo'qon",
                   "price": "9 000", "regular_price": "12 000", "discount": 25,
                   "promo_until": "20.11.2026", "address": ""}
        uz = render_text("promotion", context, "uz")
        ru = render_text("promotion", context, "ru")
        self.assertIn("Hozir 9 000 so'm, avval 12 000 so'm edi (−25%)", uz)
        self.assertIn("Сейчас 9 000 сум вместо 12 000 сум (−25%)", ru)
        self.assertIn("20.11.2026 gacha amal qiladi", uz)
        self.assertNotIn("Address", uz)

    def test_plural_forms(self):
        from .generators import render_text

        context = {"store": "Havas", "city": "Andijon", "district": "",
                   "address": "", "product_count": 5}
        self.assertIn("5 ta mahsulot", render_text("new_store", context, "uz"))
        self.assertIn("цены 5 товаров", render_text("new_store", context, "ru"))
        context["product_count"] = 1
        self.assertIn("цену 1 товара", render_text("new_store", context, "ru"))

    def test_som_filter(self):
        from core.templatetags.formatting import som

        self.assertEqual(som(1234567), "1 234 567")
        self.assertEqual(som("950"), "950")
        self.assertEqual(som(None), None)
