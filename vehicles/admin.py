from django.contrib import admin

from .models import Agency, Vehicle


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ["name", "city", "phone"]


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["plate", "brand", "model", "year", "mileage", "agency", "status", "is_rentable", "daily_rate", "is_for_sale", "sale_price"]
    list_filter = ["status", "agency", "category", "fuel", "is_rentable", "is_for_sale"]
    search_fields = ["plate", "vin", "brand", "model"]
    list_editable = ["status", "is_rentable", "is_for_sale"]
