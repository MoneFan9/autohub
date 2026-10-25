from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from payments.models import Payment
from payments.providers import PaymentDeclined
from rentals import pricing, services
from rentals.models import Booking
from vehicles.models import Vehicle

D = timedelta(days=1)


def book(vehicle, customer, start, end, **kw):
    return services.create_booking(vehicle=vehicle, customer=customer, start=start, end=end, **kw)


class TestPricing:
    def test_partial_day_counts_as_full_day(self, vehicle, t0):
        assert pricing.quote(vehicle, t0, t0 + timedelta(hours=25)).days == 2

    def test_weekly_discount_and_capped_extra(self, vehicle, gps, t0):
        q = pricing.quote(vehicle, t0, t0 + 7 * D, [gps])
        assert q.base_amount == Decimal("280.00")
        assert q.discount_amount == Decimal("28.00")
        assert q.extras_amount == Decimal("20.00")  # plafonné
        assert q.total_amount == Decimal("272.00")
        assert q.deposit_amount == Decimal("300.00")

    def test_end_before_start_rejected(self, vehicle, t0):
        with pytest.raises(ValueError):
            pricing.quote(vehicle, t0, t0)


class TestAvailability:
    def test_overlap_rejected_by_service(self, vehicle, customer, t0):
        book(vehicle, customer, t0, t0 + 3 * D)
        with pytest.raises(services.VehicleUnavailable):
            book(vehicle, customer, t0 + 2 * D, t0 + 5 * D)

    def test_back_to_back_allowed(self, vehicle, customer, t0):
        book(vehicle, customer, t0, t0 + 2 * D)
        book(vehicle, customer, t0 + 2 * D, t0 + 4 * D)

    def test_constraint_enforced_in_database(self, vehicle, customer, t0):
        b = book(vehicle, customer, t0, t0 + 3 * D)
        b.pk, b.reference = None, "AH-DUPLICAT"
        with pytest.raises(IntegrityError), transaction.atomic():
            b.save()

    def test_cancelled_booking_frees_slot(self, vehicle, customer, t0):
        services.cancel_booking(book(vehicle, customer, t0, t0 + 3 * D))
        book(vehicle, customer, t0, t0 + 3 * D)

    def test_available_between(self, vehicle, customer, t0):
        book(vehicle, customer, t0, t0 + 3 * D)
        assert not Vehicle.objects.available_between(t0 + D, t0 + 2 * D).exists()
        assert Vehicle.objects.available_between(t0 + 3 * D, t0 + 4 * D).exists()

    def test_maintenance_vehicle_not_bookable(self, vehicle, customer, t0):
        Vehicle.objects.filter(pk=vehicle.pk).update(status=Vehicle.Status.MAINTENANCE)
        with pytest.raises(services.VehicleUnavailable):
            book(vehicle, customer, t0, t0 + D)


class TestDriverRules:
    def test_young_driver_rejected(self, vehicle, customer, t0):
        customer.birth_date = date.today().replace(year=date.today().year - 19)
        with pytest.raises(services.BookingError, match="21 ans"):
            book(vehicle, customer, t0, t0 + D)

    def test_recent_license_rejected(self, vehicle, customer, t0):
        customer.license_issued_on = date.today() - timedelta(days=200)
        with pytest.raises(services.BookingError, match="permis"):
            book(vehicle, customer, t0, t0 + D)


class TestLifecycle:
    def test_full_cycle(self, vehicle, customer, t0):
        b = services.pay_and_confirm(book(vehicle, customer, t0, t0 + 2 * D), "tok_visa")
        assert b.status == Booking.Status.CONFIRMED
        assert set(b.payments.values_list("kind", flat=True)) == {"charge", "deposit_hold"}

        services.start_rental(b, mileage=1000, fuel_level=100)
        vehicle.refresh_from_db()
        assert vehicle.status == Vehicle.Status.RENTED

        services.complete_rental(b, mileage=1250, fuel_level=90)
        vehicle.refresh_from_db()
        assert (vehicle.status, vehicle.mileage) == (Vehicle.Status.AVAILABLE, 1250)
        assert b.payments.filter(kind="deposit_release").exists()

    def test_damage_on_return_sends_to_workshop_and_keeps_deposit(self, vehicle, customer, t0):
        b = services.pay_and_confirm(book(vehicle, customer, t0, t0 + D), "tok_visa")
        services.start_rental(b, mileage=1000, fuel_level=100)
        services.complete_rental(b, mileage=1100, fuel_level=50, damages="Rayure portière")
        vehicle.refresh_from_db()
        assert vehicle.status == Vehicle.Status.MAINTENANCE
        assert not b.payments.filter(kind="deposit_release").exists()

    def test_return_mileage_cannot_decrease(self, vehicle, customer, t0):
        b = services.pay_and_confirm(book(vehicle, customer, t0, t0 + D), "tok_visa")
        services.start_rental(b, mileage=1000, fuel_level=100)
        with pytest.raises(services.BookingError):
            services.complete_rental(b, mileage=900, fuel_level=50)

    def test_cannot_start_unpaid_booking(self, vehicle, customer, t0):
        with pytest.raises(services.BookingError):
            services.start_rental(book(vehicle, customer, t0, t0 + D), mileage=1, fuel_level=1)

    def test_cancel_confirmed_refunds(self, vehicle, customer, t0):
        b = services.pay_and_confirm(book(vehicle, customer, t0, t0 + D), "tok_visa")
        services.cancel_booking(b)
        assert b.payments.filter(kind="refund", amount=b.total_amount).exists()

    def test_declined_card_is_traced(self, vehicle, customer, t0):
        b = book(vehicle, customer, t0, t0 + D)
        with pytest.raises(PaymentDeclined):
            services.pay_and_confirm(b, "tok_declined")
        assert Payment.objects.filter(booking=b, status="failed").exists()
        b.refresh_from_db()
        assert b.status == Booking.Status.PENDING
