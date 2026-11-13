from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from locations.models import City

from .models import Post


class PostModelTests(TestCase):
    def make_post(self, **fields):
        data = {
            "rubric": Post.Rubric.PROMOTION,
            "title": "Shakar arzonladi",
            "text": "Baraka Marketda shakar 11 000 so'm.",
        }
        data.update(fields)
        return Post(**data)

    def test_defaults(self):
        post = self.make_post()
        post.full_clean()
        post.save()
        self.assertEqual(post.status, Post.Status.DRAFT)
        self.assertEqual(post.language, Post.Language.UZBEK)
        self.assertIsNone(post.scheduled_at)
        self.assertIsNone(post.published_at)
        self.assertFalse(post.photo)
        self.assertEqual(str(post), "[Promotion] Shakar arzonladi")

    def test_choices_are_validated(self):
        for field, value in [("rubric", "weather"), ("language", "en"), ("status", "x")]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.make_post(**{field: value}).full_clean()

    def test_scheduled_post_needs_a_time(self):
        post = self.make_post(status=Post.Status.SCHEDULED)
        with self.assertRaises(ValidationError):
            post.full_clean()
        # The database refuses it too, even if validation is skipped.
        with self.assertRaises(IntegrityError), transaction.atomic():
            post.save()
        post.scheduled_at = timezone.now() + timedelta(hours=1)
        post.full_clean()
        post.save()

    def test_is_due(self):
        now = timezone.now()
        past, future = now - timedelta(minutes=1), now + timedelta(hours=1)
        scheduled = Post.Status.SCHEDULED
        self.assertTrue(self.make_post(status=scheduled, scheduled_at=past).is_due)
        self.assertFalse(self.make_post(status=scheduled, scheduled_at=future).is_due)
        self.assertFalse(self.make_post(scheduled_at=past).is_due)
        self.assertFalse(
            self.make_post(status=Post.Status.PUBLISHED, scheduled_at=past).is_due
        )

    def test_deleting_city_keeps_post(self):
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        post = self.make_post(city=city)
        post.save()
        city.delete()
        post.refresh_from_db()
        self.assertIsNone(post.city)


class PostAdminTests(TestCase):
    def test_admin_records_author(self):
        admin = get_user_model().objects.create_superuser("admin", password="pw")
        self.client.force_login(admin)
        self.assertEqual(
            self.client.get(reverse("admin:posts_post_changelist")).status_code, 200
        )
        response = self.client.post(
            reverse("admin:posts_post_add"),
            {
                "rubric": "lifehack",
                "language": "ru",
                "title": "Совет дня",
                "text": "Сравнивайте цены.",
                "status": "draft",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.get().created_by, admin)
