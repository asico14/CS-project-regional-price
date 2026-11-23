from django.contrib import admin

from .models import Category, Price, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "category", "unit_size", "unit", "is_active"]
    list_filter = ["is_active", "category", "unit"]
    search_fields = ["name", "brand"]
    list_select_related = ["category"]


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    """Prices are append-only: they can be added but never edited.

    Only superusers may delete a row, to remove an obvious typo.
    """

    list_display = [
        "product", "store", "price", "regular_price", "promo_until",
        "observed_on", "created_by",
    ]
    list_filter = ["observed_on", "store__city", "store"]
    search_fields = ["product__name", "product__brand", "store__name"]
    autocomplete_fields = ["product", "store"]
    date_hierarchy = "observed_on"
    list_select_related = ["product", "store__city", "created_by"]
    readonly_fields = ["created_by", "created_at"]

    def has_change_permission(self, request, obj=None):
        # Still allow opening the add form; block saving an existing row.
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
