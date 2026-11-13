from django.contrib import admin

from .models import Category, Price, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "unit_size", "unit", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "brand")


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    """Prices can be added and viewed here, but never edited or deleted."""

    list_display = ("product", "store", "amount", "recorded_at")
    list_filter = ("store__city", "store")
    search_fields = ("product__name", "store__name")
    date_hierarchy = "recorded_at"
    autocomplete_fields = ("product", "store")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
