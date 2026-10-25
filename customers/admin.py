from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["last_name", "first_name", "email", "phone", "license_number"]
    search_fields = ["last_name", "email", "license_number"]
