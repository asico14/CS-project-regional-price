from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from .access import staff_required


@staff_required
def index(request):
    return render(request, "core/index.html")


def health(request):
    """Simple health check: confirms the app runs and the database answers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok", "database": "ok"})
