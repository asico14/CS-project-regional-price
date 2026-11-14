from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "rubric", "language", "status", "scheduled_at", "published_at")
    list_filter = ("status", "rubric", "language", "comments_enabled", "city")
    search_fields = ("title", "text")
    date_hierarchy = "created_at"
    readonly_fields = (
        "published_at",
        "telegram_message_id",
        "error_message",
        "created_by",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
