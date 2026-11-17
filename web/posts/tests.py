from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .hashtags import (
    MAX_HASHTAGS,
    MAX_TAG_LENGTH,
    build_hashtags,
    split_extra_tags,
    to_hashtag,
)
from .models import Post


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
