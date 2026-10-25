from django.contrib import admin

from .models import Seller


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ["display_name", "kind", "city", "phone", "accepts_airtel", "accepts_moov", "accepts_card", "accepts_cash", "created_at"]
    list_filter = ["kind", "city"]
    search_fields = ["display_name", "user__username", "user__email", "phone"]
