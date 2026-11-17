from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

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
