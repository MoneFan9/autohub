from django.contrib import admin

from payments.models import Payment

from .models import Booking, Extra, Inspection


class InspectionInline(admin.TabularInline):
    model = Inspection
    extra = 0
    readonly_fields = ["created_at", "performed_by"]


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = ["kind", "status", "amount", "provider", "provider_ref", "error", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["reference", "vehicle", "customer", "period", "status", "payment_method", "total_amount", "platform_fee"]
    list_filter = ["status", "payment_method", "vehicle__agency__seller"]
    search_fields = ["reference", "customer__last_name", "customer__email", "vehicle__plate"]
    readonly_fields = ["reference", "days", "base_amount", "extras_amount", "discount_amount", "total_amount", "deposit_amount"]
    inlines = [InspectionInline, PaymentInline]


@admin.register(Extra)
class ExtraAdmin(admin.ModelAdmin):
    list_display = ["code", "label", "price_per_day", "max_price"]
