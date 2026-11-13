"""Staff-only access for the management site.

Anonymous visitors are sent to the login page; logged-in users who are
not staff get a 403 page (sending them to login again would be a loop).
"""

from functools import wraps

from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def is_staff(user):
    return user.is_authenticated and user.is_active and user.is_staff


class StaffRequiredMixin(UserPassesTestMixin):
    """For class-based views: put it first in the list of parents."""

    def test_func(self):
        return is_staff(self.request.user)


def staff_required(view_func):
    """For function-based views."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_staff(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper
