from django.test import SimpleTestCase, TestCase

from locations.models import City

from .hashtags import MAX_HASHTAGS, build_hashtags, hashtags_for_post, make_hashtag
from .models import Post


class MakeHashtagTests(SimpleTestCase):
    def test_examples(self):
        cases = {
            "aksiya": "#aksiya",
            "Qo'qon": "#Qoqon",
            "Marg‘ilon": "#Margilon",
            "Farg`ona": "#Fargona",
            "Baraka Market": "#Baraka_Market",
            "  sut - qatiq  ": "#sut_qatiq",
            "Sut 3.2%": "#Sut_32",
            "новости магазинов": "#новости_магазинов",
            "#aksiya": "#aksiya",
            "__a__b__": "#a_b",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(make_hashtag(text), expected)

    def test_text_that_cannot_be_a_hashtag(self):
        for text in ["", "   ", "!!!", "'", "2026", "20_26", "_"]:
            with self.subTest(text=text):
                self.assertEqual(make_hashtag(text), "")


class BuildHashtagsTests(SimpleTestCase):
    def test_rubric_city_and_extra_in_order(self):
        self.assertEqual(
            build_hashtags("promotion", "uz", "Qo'qon", ["shakar"]),
            ["#aksiya", "#Qoqon", "#shakar"],
        )

    def test_language_changes_rubric_tag(self):
        self.assertEqual(build_hashtags("price", "ru"), ["#цены"])
        self.assertEqual(build_hashtags("price", "uz"), ["#narxlar"])
        # An unknown language falls back to Uzbek.
        self.assertEqual(build_hashtags("price", "en"), ["#narxlar"])

    def test_every_rubric_has_a_tag_in_both_languages(self):
        for rubric in Post.Rubric.values:
            for language in Post.Language.values:
                with self.subTest(rubric=rubric, language=language):
                    self.assertEqual(len(build_hashtags(rubric, language)), 1)

    def test_duplicates_and_empty_tags_are_dropped(self):
        self.assertEqual(
            build_hashtags("promotion", "uz", "Qo'qon", ["Aksiya", "qoqon", "", "!!"]),
            ["#aksiya", "#Qoqon"],
        )

    def test_unknown_rubric_gives_no_rubric_tag(self):
        self.assertEqual(build_hashtags("weather", "uz", "Andijon"), ["#Andijon"])

    def test_number_of_hashtags_is_limited(self):
        extra = [f"soz{number}" for number in range(20)]
        self.assertEqual(len(build_hashtags("promotion", "uz", extra=extra)), MAX_HASHTAGS)


class HashtagsForPostTests(TestCase):
    def test_uses_post_rubric_language_and_city(self):
        city = City.objects.create(name="Marg'ilon", slug="margilon")
        post = Post(rubric="store_news", language="ru", city=city)
        self.assertEqual(hashtags_for_post(post), ["#новости_магазинов", "#Margilon"])
        self.assertEqual(hashtags_for_post(Post(rubric="review")), ["#sharh"])
