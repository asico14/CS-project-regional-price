from datetime import timedelta

from django.db import connection
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from catalog.models import Price, Product
from locations.models import Store
from posts.models import Post

from .permissions import staff_required

STALE_STORE_DAYS = 14


@staff_required
def index(request):
    """Dashboard: what is in the database and what the channel will post."""
    today = timezone.localdate()
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    running_promotions = Price.objects.current().filter(
        Q(promo_until__isnull=True) | Q(promo_until__gte=today),
        regular_price__isnull=False,
        store__is_active=True,
    )
    counts = {
        "products": Product.objects.filter(is_active=True).count(),
        "stores": Store.objects.filter(is_active=True).count(),
        "prices_today": Price.objects.filter(observed_on=today).count(),
        "prices_week": Price.objects.filter(
            observed_on__gt=today - timedelta(days=7)
        ).count(),
        "promotions": running_promotions.count(),
        "drafts": Post.objects.filter(status=Post.Status.DRAFT).count(),
        "scheduled": Post.objects.filter(status=Post.Status.SCHEDULED).count(),
        "published_week": Post.objects.filter(
            status=Post.Status.PUBLISHED, published_at__gte=week_ago
        ).count(),
        "failed": Post.objects.filter(status=Post.Status.FAILED).count(),
    }
    upcoming = (
        Post.objects.filter(status__in=[Post.Status.SCHEDULED, Post.Status.PUBLISHING])
        .order_by("scheduled_at")[:10]
    )
    failures = Post.objects.filter(status=Post.Status.FAILED).order_by("-updated_at")[:10]
    stale_stores = (
        Store.objects.filter(is_active=True)
        .select_related("city")
        .annotate(last_price=Max("prices__observed_on"))
        .filter(
            Q(last_price__isnull=True)
            | Q(last_price__lt=today - timedelta(days=STALE_STORE_DAYS))
        )
        .order_by("last_price")[:10]
    )
    return render(request, "core/dashboard.html", {
        "counts": counts,
        "upcoming": upcoming,
        "failures": failures,
        "stale_stores": stale_stores,
        "stale_days": STALE_STORE_DAYS,
        "now": now,
    })


def health(request):
    """Simple health check: confirms the app runs and the database answers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok", "database": "ok"})
