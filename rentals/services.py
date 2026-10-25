from django.conf import settings
from django.db import IntegrityError, transaction
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


@transaction.atomic
def create_booking(*, vehicle, customer, start, end, pickup_agency=None, return_agency=None, extras=()):
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
    if not Vehicle.objects.rentable().filter(pk=vehicle.pk).exists():
        raise VehicleUnavailable("Ce véhicule n'est pas proposé à la location.")
    check_driver(customer, start.date())
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


def pay_and_confirm(booking, payment_token):
    # Pas de transaction englobante : un paiement refusé doit rester tracé.
    _require(booking, Booking.Status.PENDING)
    payment_services.charge_booking(booking, payment_token)
    booking.status = Booking.Status.CONFIRMED
    booking.save(update_fields=["status", "updated_at"])
    return booking


@transaction.atomic
def start_rental(booking, *, mileage, fuel_level, damages="", user=None):
    _require(booking, Booking.Status.CONFIRMED)
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
