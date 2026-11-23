"""Access control for the staff pages.

The site is a back office for the channel editors: every page except the
login page and the health check is for staff users only.

* not logged in       -> redirected to the login page
* logged in, no staff -> 403 Forbidden
"""

from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def staff_required(view):
    """Decorator for function-based views."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


class StaffRequiredMixin(AccessMixin):
    """Mixin for class-based views; put it first in the base class list."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
