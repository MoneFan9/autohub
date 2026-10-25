from django.contrib import admin

from .models import Seller, TermsAcceptance


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ["display_name", "kind", "city", "phone", "accepts_airtel", "accepts_moov", "accepts_card", "accepts_cash", "created_at"]
    list_filter = ["kind", "city"]
    search_fields = ["display_name", "user__username", "user__email", "phone"]


@admin.register(TermsAcceptance)
class TermsAcceptanceAdmin(admin.ModelAdmin):
    list_display = ["user", "document", "version", "accepted_at"]
    list_filter = ["document", "version"]
    readonly_fields = ["user", "document", "version", "accepted_at"]
