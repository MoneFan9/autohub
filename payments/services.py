from .models import Payment
from .providers import PaymentDeclined, get_provider


def method_from_token(token):
    """« airtel_ok », « moov_declined », « tok_visa »… -> moyen de paiement."""
    prefix = (token or "").split("_", 1)[0]
    return prefix if prefix in Payment.Method.values else Payment.Method.CARD


def _record(booking, kind, amount, provider, ref="", status=Payment.Status.SUCCEEDED, error="", method=""):
    return Payment.objects.create(
        booking=booking, kind=kind, amount=amount, provider=provider.name,
        provider_ref=ref, status=status, error=error, method=method,
    )


def charge_booking(booking, token):
    provider = get_provider()
    method = method_from_token(token)
    try:
        charge_ref = provider.charge(booking.total_amount, token)
        hold_ref = provider.hold(booking.deposit_amount, token)
    except PaymentDeclined as exc:
        _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider,
                status=Payment.Status.FAILED, error=str(exc), method=method)
        raise
    _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider, charge_ref, method=method)
    _record(booking, Payment.Kind.DEPOSIT_HOLD, booking.deposit_amount, provider, hold_ref, method=method)


def record_cash(booking):
    """L'agence a reçu en espèces le solde de la location et la caution."""
    provider = get_provider()
    due = balance_due(booking)
    if due > 0:
        _record(booking, Payment.Kind.CHARGE, due, provider, "espèces", method=Payment.Method.CASH)
    if not booking.payments.filter(kind=Payment.Kind.DEPOSIT_HOLD, status=Payment.Status.SUCCEEDED).exists():
        _record(booking, Payment.Kind.DEPOSIT_HOLD, booking.deposit_amount, provider, "espèces", method=Payment.Method.CASH)


def amount_paid(booking):
    from django.db.models import Sum

    ok = booking.payments.filter(status=Payment.Status.SUCCEEDED)
    charged = ok.filter(kind=Payment.Kind.CHARGE).aggregate(s=Sum("amount"))["s"] or 0
    refunded = ok.filter(kind=Payment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or 0
    return charged - refunded


def balance_due(booking):
    return max(booking.total_amount - amount_paid(booking), 0)


def release_deposit(booking):
    provider = get_provider()
    hold = booking.payments.filter(kind=Payment.Kind.DEPOSIT_HOLD, status=Payment.Status.SUCCEEDED).first()
    if hold:
        _record(booking, Payment.Kind.DEPOSIT_RELEASE, hold.amount, provider, provider.release(hold.provider_ref))


def refund_booking(booking):
    provider = get_provider()
    charge = booking.payments.filter(kind=Payment.Kind.CHARGE, status=Payment.Status.SUCCEEDED).first()
    if charge:
        _record(booking, Payment.Kind.REFUND, charge.amount, provider, provider.refund(charge.provider_ref, charge.amount))
    release_deposit(booking)


def total_revenue(qs=None):
    from django.db.models import Sum

    qs = qs if qs is not None else Payment.objects.all()
    ok = qs.filter(status=Payment.Status.SUCCEEDED)
    charged = ok.filter(kind=Payment.Kind.CHARGE).aggregate(s=Sum("amount"))["s"] or 0
    refunded = ok.filter(kind=Payment.Kind.REFUND).aggregate(s=Sum("amount"))["s"] or 0
    return charged - refunded
