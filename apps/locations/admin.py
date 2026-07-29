from django.contrib import admin
from .models import Region, District, Town, Area


class DistrictInline(admin.TabularInline):
    model = District
    extra = 1
    prepopulated_fields = {"slug": ("name",)}


class TownInline(admin.TabularInline):
    model = Town
    extra = 1
    prepopulated_fields = {"slug": ("name",)}


class AreaInline(admin.TabularInline):
    model = Area
    extra = 1
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "slug", "created_at")
    list_filter = ("region",)
    search_fields = ("name", "region__name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["region"]
    inlines = [TownInline]


@admin.register(Town)
class TownAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "slug", "created_at")
    list_filter = ("district__region", "district")
    search_fields = ("name", "district__name", "district__region__name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["district"]
    inlines = [AreaInline]


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "town", "slug", "created_at")
    list_filter = ("town__district__region", "town__district", "town")
    search_fields = ("name", "town__name", "town__district__name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["town"]