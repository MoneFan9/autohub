from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Sum

from .models import Payment
from .providers import PaymentDeclined, get_provider

MOBILE_MONEY = ("airtel", "moov")


def method_from_token(token):
    """« airtel_ok », « moov_declined », « tok_visa »… -> moyen de paiement."""
    prefix = (token or "").split("_", 1)[0]
    return prefix if prefix in Payment.Method.values else Payment.Method.CARD


def platform_fee(amount):
    if not settings.FEES_ACTIVE:
        return Decimal("0")
    return (Decimal(amount) * Decimal(settings.PLATFORM_FEE_RATE)).quantize(Decimal("1"), ROUND_HALF_UP)


def _record(booking, kind, amount, provider_name, ref="", status=Payment.Status.SUCCEEDED, error="", method="", number=""):
    return Payment.objects.create(
        booking=booking, kind=kind, amount=amount, provider=provider_name,
        provider_ref=ref, status=status, error=error, method=method, payer_number=number,
    )


def charge_booking(booking, token):
    """Paiement immédiat (carte ou jeton de test)."""
    provider = get_provider()
    method = method_from_token(token)
    try:
        ref = provider.charge(booking.total_amount, token)
    except PaymentDeclined as exc:
        _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider.name,
                status=Payment.Status.FAILED, error=str(exc), method=method)
        raise
    _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider.name, ref, method=method)


def request_mobile_payment(booking, method, number):
    """Envoie une demande de paiement Mobile Money au numéro du client."""
    provider = get_provider()
    ref = provider.request_payment(booking.total_amount, number, method)
    return _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider.name, ref,
                   status=Payment.Status.PENDING, method=method, number=number)


def pending_payment(booking):
    return booking.payments.filter(kind=Payment.Kind.CHARGE, status=Payment.Status.PENDING).first()


def check_mobile_payment(payment):
    """Interroge le prestataire ; renvoie le statut à jour du paiement."""
    if payment.status != Payment.Status.PENDING:
        return payment.status
    status = get_provider().payment_status(payment.provider_ref, payment.payer_number)
    if status == "succeeded":
        payment.status = Payment.Status.SUCCEEDED
    elif status == "failed":
        payment.status, payment.error = Payment.Status.FAILED, "Paiement refusé ou non validé."
    payment.save(update_fields=["status", "error"])
    return payment.status


def record_handover(booking, *, cash_for_rental):
    """Remise des clés : le loueur reçoit la caution (et la location si paiement en espèces)."""
    due = balance_due(booking)
    if cash_for_rental and due > 0:
        _record(booking, Payment.Kind.CHARGE, due, "agence", "espèces", method=Payment.Method.CASH)
    if not booking.payments.filter(kind=Payment.Kind.DEPOSIT_HOLD, status=Payment.Status.SUCCEEDED).exists():
        _record(booking, Payment.Kind.DEPOSIT_HOLD, booking.deposit_amount, "agence", "remise des clés", method=Payment.Method.CASH)


def amount_paid(booking):
    ok = booking.payments.filter(status=Payment.Status.SUCCEEDED)
    charged = ok.filter(kind=Payment.Kind.CHARGE).aggregate(s=Sum("amount"))["s"] or 0
    refunded = ok.filter(kind=Payment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or 0
    return charged - refunded


def balance_due(booking):
    return max(booking.total_amount - amount_paid(booking), 0)


def release_deposit(booking):
    hold = booking.payments.filter(kind=Payment.Kind.DEPOSIT_HOLD, status=Payment.Status.SUCCEEDED).first()
    if hold:
        _record(booking, Payment.Kind.DEPOSIT_RELEASE, hold.amount, hold.provider, "caution rendue", method=hold.method)


def refund_booking(booking):
    """Rembourse ce qui a été payé en ligne. Les espèces se règlent entre client et loueur."""
    provider = get_provider()
    for charge in booking.payments.filter(kind=Payment.Kind.CHARGE, status=Payment.Status.SUCCEEDED).exclude(method=Payment.Method.CASH):
        _record(booking, Payment.Kind.REFUND, charge.amount, provider.name,
                provider.refund(charge.provider_ref, charge.amount), method=charge.method, number=charge.payer_number)
    release_deposit(booking)


def total_revenue(qs=None):
    qs = qs if qs is not None else Payment.objects.all()
    ok = qs.filter(status=Payment.Status.SUCCEEDED)
    charged = ok.filter(kind=Payment.Kind.CHARGE).aggregate(s=Sum("amount"))["s"] or 0
    refunded = ok.filter(kind=Payment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or 0
    return charged - refunded
