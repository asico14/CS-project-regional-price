from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .comments import CLOSE, KEEP, WAIT, decide
from .models import Post


class CommentDecisionTests(TestCase):
    def make_post(self, **fields):
        data = {"rubric": "price", "title": "Post", "text": "Matn", "status": "published"}
        data.update(fields)
        return Post.objects.create(**data)

    def test_comments_stay_open_by_default(self):
        self.make_post(telegram_message_id=101)
        self.assertEqual(decide(101), KEEP)

    def test_comments_are_closed_when_switched_off(self):
        self.make_post(telegram_message_id=101, comments_enabled=False)
        self.make_post(telegram_message_id=102)
        self.assertEqual(decide(101), CLOSE)
        self.assertEqual(decide(102), KEEP)

    def test_message_that_is_not_our_post_is_left_alone(self):
        self.make_post(telegram_message_id=101, comments_enabled=False)
        self.assertEqual(decide(999), KEEP)

    def test_waits_while_a_post_is_still_being_published(self):
        post = self.make_post(status="publishing", comments_enabled=False)
        self.assertEqual(decide(555), WAIT)
        # The worker saves the message id; now the answer is known.
        post.status, post.telegram_message_id = "published", 555
        post.save()
        self.assertEqual(decide(555), CLOSE)


class CommentFormTests(TestCase):
    def setUp(self):
        staff = get_user_model().objects.create_user("staff", password="pw", is_staff=True)
        self.client.force_login(staff)
        self.data = {
            "rubric": "lifehack",
            "language": "uz",
            "title": "Maslahat",
            "text": "Matn",
            "status": "draft",
        }

    def test_new_post_form_has_comments_switched_on(self):
        form = self.client.get(reverse("post_create")).context["form"]
        self.assertTrue(form.fields["comments_enabled"].initial)

    def test_comments_can_be_switched_off_and_on(self):
        self.client.post(reverse("post_create"), self.data)
        post = Post.objects.get()
        self.assertFalse(post.comments_enabled)  # unchecked box
        url = reverse("post_update", args=[post.pk])
        self.client.post(url, {**self.data, "comments_enabled": "on"})
        post.refresh_from_db()
        self.assertTrue(post.comments_enabled)


class PostFormUnitTests(TestCase):
    """PostForm used directly, without a request."""

    def test_missing_title_reports_the_field_and_skips_the_length_check(self):
        from .forms import PostForm

        form = PostForm({"rubric": "price", "language": "uz", "text": "x", "status": "draft"})
        self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors), ["title"])

    def test_save_writes_to_the_database_and_clears_the_old_error(self):
        from .forms import PostForm

        post = Post.objects.create(
            rubric="price", title="Eski", text="x", status="failed", error_message="Boom"
        )
        data = {"rubric": "price", "language": "ru", "title": "Yangi", "text": "x", "status": "draft"}
        form = PostForm(data, instance=post)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        post.refresh_from_db()
        self.assertEqual(
            (post.title, post.language, post.status, post.error_message),
            ("Yangi", "ru", "draft", ""),
        )
