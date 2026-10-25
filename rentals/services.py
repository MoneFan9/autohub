from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from psycopg.types.range import Range

from payments import services as payment_services
from vehicles.models import Vehicle

from . import pricing
from .models import Booking, Inspection


class BookingError(Exception):
    pass


class VehicleUnavailable(BookingError):
    pass


def check_driver(customer, on_date):
    if customer.age(on_date) < settings.RENTAL_MIN_DRIVER_AGE:
        raise BookingError(f"Le conducteur doit avoir au moins {settings.RENTAL_MIN_DRIVER_AGE} ans.")
    if customer.license_years(on_date) < settings.RENTAL_MIN_LICENSE_YEARS:
        raise BookingError(f"Le permis doit avoir au moins {settings.RENTAL_MIN_LICENSE_YEARS} ans.")


def expire_stale_pending(vehicle=None):
    """Libère les véhicules bloqués par une demande de paiement jamais validée."""
    limit = timezone.now() - timedelta(minutes=settings.PENDING_PAYMENT_MINUTES)
    stale = Booking.objects.filter(status=Booking.Status.PENDING, created_at__lt=limit)
    if vehicle is not None:
        stale = stale.filter(vehicle=vehicle)
    for booking in stale:
        booking.payments.filter(status="pending").update(status="failed", error="Demande de paiement expirée.")
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])


@transaction.atomic
def create_booking(*, vehicle, customer, start, end, pickup_agency=None, return_agency=None, extras=()):
    expire_stale_pending(vehicle)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if not Vehicle.objects.rentable().filter(pk=vehicle.pk).exists():
        raise VehicleUnavailable("Ce véhicule n'est pas proposé à la location.")
    check_driver(customer, start.date())
    if return_agency is not None and return_agency.seller_id != vehicle.agency.seller_id:
        raise BookingError("Le lieu de retour doit appartenir au même loueur.")
    q = pricing.quote(vehicle, start, end, extras)
    booking = Booking(
        vehicle=vehicle,
        customer=customer,
        pickup_agency=pickup_agency or vehicle.agency,
        return_agency=return_agency or pickup_agency or vehicle.agency,
        period=Range(start, end, "[)"),
        days=q.days,
        base_amount=q.base_amount,
        extras_amount=q.extras_amount,
        discount_amount=q.discount_amount,
        total_amount=q.total_amount,
        deposit_amount=q.deposit_amount,
    )
    try:
        with transaction.atomic():
            booking.save()
    except IntegrityError as exc:
        if "no_overlapping_bookings" in str(exc):
            raise VehicleUnavailable("Ce véhicule est déjà réservé sur cette période.") from exc
        raise
    booking.extras.set(extras)
    return booking


def _require(booking, *statuses):
    if booking.status not in statuses:
        raise BookingError(f"Action impossible : réservation {booking.get_status_display().lower()}.")


CASH_TOKEN = "cash_ok"


def _confirm(booking, method):
    booking.payment_method = method
    booking.platform_fee = payment_services.platform_fee(booking.total_amount)
    booking.status = Booking.Status.CONFIRMED
    booking.save(update_fields=["payment_method", "platform_fee", "status", "updated_at"])
    return booking


def pay_and_confirm(booking, payment_token):
    """Paiement immédiat (carte, espèces, jetons de test de l'API)."""
    # Pas de transaction englobante : un paiement refusé doit rester tracé.
    _require(booking, Booking.Status.PENDING)
    method = payment_services.method_from_token(payment_token)
    if payment_token != CASH_TOKEN:
        # Espèces : rien n'est encaissé en ligne, le loueur encaisse à la remise des clés.
        payment_services.charge_booking(booking, payment_token)
    return _confirm(booking, method)


def start_mobile_payment(booking, method, number):
    """Mobile Money : envoie la demande de paiement ; la réservation attend la validation du client."""
    _require(booking, Booking.Status.PENDING)
    booking.payment_method = method
    booking.save(update_fields=["payment_method", "updated_at"])
    return payment_services.request_mobile_payment(booking, method, number)


def finalize_mobile_payment(booking):
    """Interroge le prestataire : confirme ou annule la réservation. Renvoie le statut du paiement."""
    payment = payment_services.pending_payment(booking) or booking.payments.filter(kind="charge").order_by("-created_at").first()
    if payment is None:
        return None
    status = payment_services.check_mobile_payment(payment)
    if status == "succeeded" and booking.status == Booking.Status.PENDING:
        _confirm(booking, payment.method)
    elif status == "failed" and booking.status == Booking.Status.PENDING:
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
    return status


@transaction.atomic
def start_rental(booking, *, mileage, fuel_level, damages="", user=None, handover_received=False):
    _require(booking, Booking.Status.CONFIRMED)
    if not handover_received:
        due = payment_services.balance_due(booking)
        what = f"{due:.0f} FCFA en espèces + " if due > 0 else ""
        raise BookingError(f"À recevoir avant la remise des clés : {what}caution {booking.deposit_amount:.0f} FCFA.")
    payment_services.record_handover(booking, cash_for_rental=booking.payment_method == "cash")
    Inspection.objects.create(
        booking=booking, kind=Inspection.Kind.PICKUP, mileage=mileage,
        fuel_level=fuel_level, damages=damages, performed_by=user,
    )
    booking.status = Booking.Status.ACTIVE
    booking.save(update_fields=["status", "updated_at"])
    Vehicle.objects.filter(pk=booking.vehicle_id).update(status=Vehicle.Status.RENTED, mileage=mileage)
    return booking


@transaction.atomic
def complete_rental(booking, *, mileage, fuel_level, damages="", user=None):
    _require(booking, Booking.Status.ACTIVE)
    pickup = booking.inspections.get(kind=Inspection.Kind.PICKUP)
    if mileage < pickup.mileage:
        raise BookingError("Le kilométrage de retour est inférieur à celui du départ.")
    Inspection.objects.create(
        booking=booking, kind=Inspection.Kind.RETURN, mileage=mileage,
        fuel_level=fuel_level, damages=damages, performed_by=user,
    )
    booking.status = Booking.Status.COMPLETED
    booking.save(update_fields=["status", "updated_at"])
    new_status = Vehicle.Status.MAINTENANCE if damages.strip() else Vehicle.Status.AVAILABLE
    Vehicle.objects.filter(pk=booking.vehicle_id).update(
        status=new_status, mileage=mileage, agency=booking.return_agency
    )
    if not damages.strip():
        payment_services.release_deposit(booking)
    return booking


@transaction.atomic
def cancel_booking(booking):
    _require(booking, Booking.Status.PENDING, Booking.Status.CONFIRMED)
    if booking.status == Booking.Status.CONFIRMED:
        payment_services.refund_booking(booking)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    return booking
