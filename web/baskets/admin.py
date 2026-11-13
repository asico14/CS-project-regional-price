from django.contrib import admin

from .models import Basket, BasketItem


class BasketItemInline(admin.TabularInline):
    model = BasketItem
    extra = 1
    autocomplete_fields = ("product",)


@admin.register(Basket)
class BasketAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "created_at")
    search_fields = ("name",)
    inlines = [BasketItemInline]
