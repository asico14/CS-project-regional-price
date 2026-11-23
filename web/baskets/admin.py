from django.contrib import admin

from .models import Basket, BasketItem


class BasketItemInline(admin.TabularInline):
    model = BasketItem
    extra = 1
    autocomplete_fields = ["product"]


@admin.register(Basket)
class BasketAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    inlines = [BasketItemInline]
