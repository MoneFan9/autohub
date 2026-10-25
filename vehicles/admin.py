from django.contrib import admin

from .models import Agency, Report, Vehicle, VehicleBlock, VehiclePhoto


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone", "seller"]


class PhotoInline(admin.TabularInline):
    model = VehiclePhoto
    extra = 0
    fields = ["image", "kind", "position"]


class BlockInline(admin.TabularInline):
    model = VehicleBlock
    extra = 0


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["plate", "brand", "model", "year", "mileage", "agency", "status", "is_rentable", "daily_rate", "is_for_sale", "sale_price"]
    list_filter = ["status", "category", "fuel", "is_rentable", "is_for_sale", "agency__seller"]
    search_fields = ["plate", "vin", "brand", "model", "agency__seller__display_name"]
    list_editable = ["status", "is_rentable", "is_for_sale"]
    inlines = [PhotoInline, BlockInline]


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["vehicle", "reason", "created_at", "handled"]
    list_filter = ["handled", "reason"]
    list_editable = ["handled"]
    readonly_fields = ["vehicle", "reason", "message", "reporter", "contact", "created_at"]
