"""Helpers shared by the test suites of all apps."""

from django.contrib.auth import get_user_model
from django.test import TestCase

PASSWORD = "secret-pass-123"


def make_user(username="editor", staff=True, **extra):
    return get_user_model().objects.create_user(
        username, password=PASSWORD, is_staff=staff, **extra
    )


class StaffTestCase(TestCase):
    """A TestCase whose client is logged in as a staff user."""

    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client.force_login(self.user)

    def assertStaffOnly(self, url):
        """Anonymous users are sent to the login page, non-staff get 403."""
        from django.test import Client

        anonymous = Client().get(url)
        self.assertEqual(anonymous.status_code, 302, url)
        self.assertTrue(anonymous.url.startswith("/login/"), url)
        outsider = Client()
        user = get_user_model().objects.filter(username="outsider").first()
        outsider.force_login(user or make_user("outsider", staff=False))
        self.assertEqual(outsider.get(url).status_code, 403, url)
