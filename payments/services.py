from .models import Payment
from .providers import PaymentDeclined, get_provider


def _record(booking, kind, amount, provider, ref="", status=Payment.Status.SUCCEEDED, error=""):
    return Payment.objects.create(
        booking=booking, kind=kind, amount=amount, provider=provider.name,
        provider_ref=ref, status=status, error=error,
    )


def charge_booking(booking, token):
    provider = get_provider()
    try:
        charge_ref = provider.charge(booking.total_amount, token)
        hold_ref = provider.hold(booking.deposit_amount, token)
    except PaymentDeclined as exc:
        _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider,
                status=Payment.Status.FAILED, error=str(exc))
        raise
    _record(booking, Payment.Kind.CHARGE, booking.total_amount, provider, charge_ref)
    _record(booking, Payment.Kind.DEPOSIT_HOLD, booking.deposit_amount, provider, hold_ref)


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
