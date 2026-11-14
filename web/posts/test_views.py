import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from locations.models import City

from .formatting import compose_text, limit_for, telegram_length
from .forms import DATETIME_FORMAT
from .models import Post

MEDIA_ROOT = tempfile.mkdtemp()


def png_file(name="photo.png"):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "green").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class FormattingTests(SimpleTestCase):
    def test_compose_text_skips_empty_parts(self):
        self.assertEqual(
            compose_text(" Sarlavha ", "Matn\n", ["#a", "#b"]), "Sarlavha\n\nMatn\n\n#a #b"
        )
        self.assertEqual(compose_text("Sarlavha", "", []), "Sarlavha")

    def test_length_is_counted_like_telegram(self):
        self.assertEqual(telegram_length("salom"), 5)
        self.assertEqual(telegram_length("привет"), 6)
        # One emoji is two UTF-16 units for Telegram.
        self.assertEqual(telegram_length("🔥"), 2)

    def test_limits(self):
        self.assertEqual((limit_for(False), limit_for(True)), (4096, 1024))


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class PostViewTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            "staff", password="pw", is_staff=True
        )
        self.client.force_login(self.staff)
        self.city = City.objects.create(name="Qo'qon", slug="qoqon")

    def form_data(self, **changes):
        data = {
            "rubric": "promotion",
            "language": "uz",
            "city": self.city.pk,
            "title": "Shakar arzonladi",
            "text": "Baraka Marketda shakar 11 000 so'm.",
            "status": "draft",
            "scheduled_at": "",
        }
        data.update(changes)
        return data

    def in_hours(self, hours):
        moment = timezone.localtime(timezone.now() + timedelta(hours=hours))
        return moment.strftime(DATETIME_FORMAT)


class PostFormTests(PostViewTestCase):
    def test_pages_require_staff(self):
        self.client.logout()
        for url in [reverse("post_list"), reverse("post_create")]:
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.client.post(reverse("post_create"), self.form_data())
        self.assertEqual(self.client.post(reverse("post_preview")).status_code, 302)
        self.assertFalse(Post.objects.exists())

    def test_create_draft_records_author(self):
        response = self.client.post(
            reverse("post_create"), self.form_data(text="Birinchi qator\r\nIkkinchi")
        )
        self.assertRedirects(response, reverse("post_list"))
        post = Post.objects.get()
        self.assertEqual(post.status, Post.Status.DRAFT)
        self.assertEqual(post.created_by, self.staff)
        self.assertEqual(post.text, "Birinchi qator\nIkkinchi")

    def test_schedule_post(self):
        self.client.post(
            reverse("post_create"),
            self.form_data(status="scheduled", scheduled_at=self.in_hours(2)),
        )
        post = Post.objects.get()
        self.assertEqual(post.status, Post.Status.SCHEDULED)
        self.assertGreater(post.scheduled_at, timezone.now() + timedelta(hours=1))

    def test_schedule_needs_a_future_time(self):
        for when in ["", self.in_hours(-1), "not a date"]:
            with self.subTest(when=when):
                response = self.client.post(
                    reverse("post_create"),
                    self.form_data(status="scheduled", scheduled_at=when),
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["form"].errors["scheduled_at"]), 1)
                self.assertFalse(Post.objects.exists())

    def test_text_post_limit_counts_title_and_hashtags(self):
        # "Shakar arzonladi" + blank line + text + blank line + "#aksiya #Qoqon"
        overhead = telegram_length(compose_text("Shakar arzonladi", "x", ["#aksiya", "#Qoqon"])) - 1
        fits = "a" * (4096 - overhead)
        response = self.client.post(reverse("post_create"), self.form_data(text=fits))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("post_create"), self.form_data(title="Yana", text=fits + "abcdefghijklmn")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Shorten it by 2.", response.context["form"].errors["text"][0])
        self.assertEqual(Post.objects.count(), 1)

    def test_photo_post_has_the_shorter_caption_limit(self):
        text = "a" * 1500
        response = self.client.post(
            reverse("post_create"), self.form_data(text=text, photo=png_file())
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("allows 1024", response.context["form"].errors["text"][0])
        response = self.client.post(reverse("post_create"), self.form_data(text=text))
        self.assertEqual(response.status_code, 302)

    def test_photo_is_saved(self):
        self.client.post(reverse("post_create"), self.form_data(photo=png_file()))
        self.assertTrue(Post.objects.get().photo.name.endswith(".png"))

    def test_file_that_is_not_an_image_is_rejected(self):
        fake = SimpleUploadedFile("photo.png", b"not an image", content_type="image/png")
        response = self.client.post(reverse("post_create"), self.form_data(photo=fake))
        self.assertIn("photo", response.context["form"].errors)

    def test_edit_failed_post_and_schedule_again(self):
        post = Post.objects.create(
            rubric="promotion",
            title="Eski",
            text="Matn",
            status=Post.Status.FAILED,
            error_message="Chat not found",
            scheduled_at=timezone.now() - timedelta(days=1),
        )
        url = reverse("post_update", args=[post.pk])
        response = self.client.get(url)
        self.assertContains(response, "Chat not found")
        self.assertEqual(response.context["form"].initial["status"], "draft")
        self.client.post(
            url, self.form_data(status="scheduled", scheduled_at=self.in_hours(1))
        )
        post.refresh_from_db()
        self.assertEqual(post.status, Post.Status.SCHEDULED)
        self.assertEqual(post.error_message, "")
        self.assertIsNone(post.created_by)

    def test_published_post_cannot_be_edited(self):
        post = Post.objects.create(
            rubric="promotion", title="Chiqqan", text="Matn", status=Post.Status.PUBLISHED
        )
        url = reverse("post_update", args=[post.pk])
        self.assertRedirects(self.client.get(url), reverse("post_list"))
        self.client.post(url, self.form_data(title="O'zgardi"))
        post.refresh_from_db()
        self.assertEqual((post.title, post.status), ("Chiqqan", Post.Status.PUBLISHED))

    def test_status_cannot_be_set_to_published_by_hand(self):
        response = self.client.post(
            reverse("post_create"), self.form_data(status="published")
        )
        self.assertIn("status", response.context["form"].errors)


class PostListTests(PostViewTestCase):
    def test_list_and_status_filter(self):
        Post.objects.create(rubric="price", title="Qoralama", text="x")
        Post.objects.create(
            rubric="price", title="Xato", text="x", status="failed", error_message="Boom"
        )
        response = self.client.get(reverse("post_list"))
        self.assertEqual(len(response.context["posts"]), 2)
        self.assertContains(response, "Boom")
        response = self.client.get(reverse("post_list"), {"status": "failed"})
        self.assertEqual([post.title for post in response.context["posts"]], ["Xato"])
        response = self.client.get(reverse("post_list"), {"status": "nonsense"})
        self.assertEqual(len(response.context["posts"]), 2)


class PostPreviewTests(PostViewTestCase):
    def preview(self, **fields):
        data = {"rubric": "promotion", "language": "uz", "title": "Salom", "text": "Matn"}
        data.update(fields)
        return self.client.post(reverse("post_preview"), data).json()

    def test_preview_matches_what_will_be_sent(self):
        data = self.preview(city=self.city.pk, text="Bir\r\nIkki")
        self.assertEqual(data["hashtags"], ["#aksiya", "#Qoqon"])
        self.assertEqual(data["text"], "Bir\nIkki")
        expected = telegram_length("Salom\n\nBir\nIkki\n\n#aksiya #Qoqon")
        self.assertEqual((data["length"], data["limit"], data["over"]), (expected, 4096, 0))

    def test_preview_reports_overflow_for_photo_posts(self):
        data = self.preview(text="a" * 1100, has_photo="1")
        self.assertEqual(data["limit"], 1024)
        self.assertEqual(data["over"], data["length"] - 1024)

    def test_preview_uses_language_and_survives_bad_input(self):
        self.assertEqual(self.preview(language="ru")["hashtags"], ["#акции"])
        data = self.preview(rubric="", language="", city="abc", title="", text="")
        self.assertEqual((data["hashtags"], data["length"]), ([], 0))

    def test_preview_is_post_only(self):
        self.assertEqual(self.client.get(reverse("post_preview")).status_code, 405)
