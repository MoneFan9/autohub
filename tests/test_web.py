from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model

from rentals.models import Booking


def test_home_search_lists_vehicle(client, vehicle):
    r = client.get("/")
    assert r.status_code == 200 and "Renault Clio" in r.content.decode()
    # Les cartes pointent vers la fiche publique, pas vers l'API.
    assert f'href="/vehicules/{vehicle.pk}/?' in r.content.decode()


def test_booking_through_website(client, vehicle, gps, t0):
    fmt = "%Y-%m-%dT%H:%M"
    data = {
        "start": t0.strftime(fmt), "end": (t0 + timedelta(days=2)).strftime(fmt), "extras": [gps.pk],
        "first_name": "Hugo", "last_name": "Thomas", "email": "hugo@example.com", "phone": "06",
        "birth_date": "1988-02-02", "license_number": "FR7", "license_issued_on": "2010-02-02",
        "card_number": "4242 4242 4242 4242",
    }
    r = client.post(f"/vehicules/{vehicle.pk}/", data)
    assert r.status_code == 302, r.context["form"].errors if r.context else r
    booking = Booking.objects.get()
    assert booking.status == "confirmed"
    assert client.get(r["Location"]).status_code == 200


def test_confirmation_not_visible_to_other_sessions(client, vehicle, customer, t0):
    from rentals import services

    b = services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + timedelta(days=1))
    assert client.get(f"/reservation/{b.reference}/").status_code == 404


def test_backoffice_requires_staff(client, db):
    assert client.get("/agence/").status_code == 302
    client.force_login(get_user_model().objects.create_user("s", is_staff=True))
    assert client.get("/agence/").status_code == 200
    assert client.get("/agence/planning/").status_code == 200
