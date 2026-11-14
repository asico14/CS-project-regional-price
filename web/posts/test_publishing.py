import shutil
import tempfile

from django.test import TestCase, override_settings

from locations.models import City

from .models import Post
from .publishing import PublishError, build_html, build_message, escape
from .test_views import png_file

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class PublishingTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def make_post(self, **fields):
        data = {"rubric": "promotion", "title": "Shakar arzonladi", "text": "Matn"}
        data.update(fields)
        return Post.objects.create(**data)

    def test_escape(self):
        self.assertEqual(escape("a < b & c > d"), "a &lt; b &amp; c &gt; d")
        # Quotes and apostrophes stay: Uzbek text is full of them.
        self.assertEqual(escape("Qo'qon \"Baraka\""), "Qo'qon \"Baraka\"")

    def test_html_has_bold_title_text_and_hashtags(self):
        city = City.objects.create(name="Qo'qon", slug="qoqon")
        post = self.make_post(city=city, text="Birinchi qator\nIkkinchi qator")
        self.assertEqual(
            build_html(post),
            "<b>Shakar arzonladi</b>\n\nBirinchi qator\nIkkinchi qator\n\n#aksiya #Qoqon",
        )

    def test_user_text_cannot_inject_formatting(self):
        post = self.make_post(
            title="Narx < 10 000 & arzon", text='<a href="http://x">bos</a> <b>qalin</b>'
        )
        self.assertEqual(
            build_html(post),
            "<b>Narx &lt; 10 000 &amp; arzon</b>\n\n"
            '&lt;a href="http://x"&gt;bos&lt;/a&gt; &lt;b&gt;qalin&lt;/b&gt;\n\n'
            "#aksiya",
        )

    def test_text_post(self):
        message = build_message(self.make_post())
        self.assertEqual((message.kind, message.photo_path), ("text", ""))
        self.assertTrue(message.html.startswith("<b>Shakar arzonladi</b>"))

    def test_photo_post(self):
        post = self.make_post(photo=png_file())
        message = build_message(post)
        self.assertEqual(message.kind, "photo")
        self.assertEqual(message.photo_path, post.photo.path)
        self.assertIn("#aksiya", message.html)

    def test_text_limit_is_checked_on_plain_text_not_html(self):
        # "Shakar arzonladi" + 2 + text + 2 + "#aksiya" = text + 27
        fits = self.make_post(text="<" * (4096 - 27))
        message = build_message(fits)
        # Escaping makes the HTML longer than 4096; that is fine for Telegram.
        self.assertGreater(len(message.html), 4096)
        with self.assertRaisesMessage(PublishError, "4097 characters long"):
            build_message(self.make_post(text="<" * (4096 - 26)))

    def test_photo_caption_limit(self):
        build_message(self.make_post(text="a" * (1024 - 27), photo=png_file()))
        too_long = self.make_post(text="a" * (1024 - 26), photo=png_file())
        with self.assertRaisesMessage(PublishError, "1024 for a post with a photo"):
            build_message(too_long)
        # The same text without a photo is fine.
        too_long.photo = ""
        self.assertEqual(build_message(too_long).kind, "text")

    def test_emoji_count_double(self):
        with self.assertRaises(PublishError):
            build_message(self.make_post(text="🔥" * 2040))
        build_message(self.make_post(text="🔥" * 2030))

    def test_missing_photo_file(self):
        post = self.make_post(photo=png_file())
        post.photo.storage.delete(post.photo.name)
        with self.assertRaisesMessage(PublishError, "photo file is missing"):
            build_message(post)

    def test_empty_post(self):
        with self.assertRaisesMessage(PublishError, "empty"):
            build_message(self.make_post(title=" ", text="\n"))
