from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from rentals.models import Booking


@pytest.fixture
def api():
    return APIClient()


def payload(vehicle, t0, **over):
    data = {
        "vehicle": vehicle.pk, "start": t0.isoformat(), "end": (t0 + timedelta(days=3)).isoformat(),
        "extras": ["gps"], "payment_token": "tok_visa",
        "customer": {"first_name": "Léa", "last_name": "Robert", "email": "Lea@Example.com", "phone": "06",
                     "birth_date": "1990-05-01", "license_number": "FR42", "license_issued_on": "2012-01-01"},
    }
    data.update(over)
    return data


def test_search_filters_by_availability(api, vehicle, t0, gps):
    assert api.post("/api/bookings/", payload(vehicle, t0), format="json").status_code == 201
    r = api.get("/api/vehicles/", {"start": (t0 + timedelta(days=1)).isoformat(), "end": (t0 + timedelta(days=2)).isoformat()})
    assert r.json()["count"] == 0
    r = api.get("/api/vehicles/", {"start": (t0 + timedelta(days=5)).isoformat(), "end": (t0 + timedelta(days=6)).isoformat()})
    assert r.json()["count"] == 1


def test_quote(api, vehicle, t0, gps):
    r = api.post("/api/bookings/quote/", {"vehicle": vehicle.pk, "start": t0.isoformat(),
                                          "end": (t0 + timedelta(days=3)).isoformat(), "extras": ["gps"]}, format="json")
    assert r.status_code == 200
    assert r.json()["total_amount"] == "129.00"  # 120 € - 5 % (3 j) + 15 € GPS


def test_public_booking_flow_and_double_booking(api, vehicle, t0, gps):
    r = api.post("/api/bookings/", payload(vehicle, t0), format="json")
    assert r.status_code == 201, r.content
    assert r.json()["status"] == "confirmed"
    r = api.post("/api/bookings/", payload(vehicle, t0 + timedelta(days=1)), format="json")
    assert r.status_code == 409


def test_declined_payment_cancels_booking(api, vehicle, t0, gps):
    r = api.post("/api/bookings/", payload(vehicle, t0, payment_token="tok_declined"), format="json")
    assert r.status_code == 402
    assert Booking.objects.get().status == "cancelled"


def test_public_cannot_overwrite_existing_customer(api, vehicle, customer, t0, gps):
    p = payload(vehicle, t0)
    p["customer"] = {**p["customer"], "email": customer.email, "license_number": "OTHER"}
    assert api.post("/api/bookings/", p, format="json").status_code == 409
    customer.refresh_from_db()
    assert customer.license_number == "FR1"


def test_bookings_list_and_actions_are_staff_only(api, vehicle, t0, gps):
    ref = api.post("/api/bookings/", payload(vehicle, t0), format="json").json()["reference"]
    assert api.get("/api/bookings/").status_code in (401, 403)
    assert api.post(f"/api/bookings/{ref}/start/", {"mileage": 10, "fuel_level": 100}).status_code in (401, 403)

    api.force_authenticate(get_user_model().objects.create_user("staff", is_staff=True))
    r = api.post(f"/api/bookings/{ref}/start/", {"mileage": 10, "fuel_level": 100})
    assert r.status_code == 200 and r.json()["status"] == "active"
    r = api.post(f"/api/bookings/{ref}/complete/", {"mileage": 5, "fuel_level": 100})
    assert r.status_code == 409
