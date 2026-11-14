"""Numbers and lists shown on the dashboard (the home page)."""

from django.db.models import Count, Q
from django.utils import timezone

from baskets.models import Basket
from catalog.models import Price, Product
from locations.models import Store
from posts.models import Post

LIST_SIZE = 5


def dashboard_data():
    now = timezone.now()
    today = timezone.localdate()
    posts = Post.objects.aggregate(
        **{
            status: Count("pk", filter=Q(status=status))
            for status in Post.Status.values
        }
    )
    active_promotions = (
        Price.objects.current()
        .filter(is_promo=True)
        .filter(Q(promo_ends__isnull=True) | Q(promo_ends__gte=today))
        .count()
    )
    upcoming = list(
        Post.objects.filter(status=Post.Status.SCHEDULED)
        .select_related("city")
        .order_by("scheduled_at")[:LIST_SIZE]
    )
    for post in upcoming:
        # Still waiting although its time has passed: the worker may be down.
        post.overdue = post.scheduled_at <= now
    return {
        "counts": {
            "products": Product.objects.filter(is_active=True).count(),
            "stores": Store.objects.filter(is_active=True).count(),
            "prices_today": Price.objects.filter(recorded_at__date=today).count(),
            "promotions": active_promotions,
            "baskets": Basket.objects.count(),
        },
        "posts": posts,
        "upcoming": upcoming,
        "failures": list(
            Post.objects.filter(status=Post.Status.FAILED).order_by("-updated_at")[
                :LIST_SIZE
            ]
        ),
    }
