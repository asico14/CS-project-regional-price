from django.contrib import admin

from .models import City, District, Store


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ["name", "city"]
    list_filter = ["city"]
    search_fields = ["name"]


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "district", "address", "is_active"]
    list_filter = ["is_active", "city"]
    search_fields = ["name", "address"]
    autocomplete_fields = ["district"]
    list_select_related = ["city", "district"]
