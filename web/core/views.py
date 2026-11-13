from django.db import connection
from django.http import HttpResponse, JsonResponse


def index(request):
    return HttpResponse(
        "Regional Price & Deals - Fergana Valley channel platform. "
        "Admin panel: /admin/"
    )


def health(request):
    """Simple health check: confirms the app runs and the database answers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok", "database": "ok"})
