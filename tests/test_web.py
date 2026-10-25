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
        "start": t0.strftime(fmt), "end": (t0 + timedelta(days=2)).strftime(fmt), "extras": [gps.code],
        "first_name": "Hugo", "last_name": "Thomas", "email": "hugo@example.com", "phone": "06",
        "birth_date": "1988-02-02", "license_number": "FR7", "license_issued_on": "2010-02-02",
        "payment_method": "airtel", "mobile_number": "+241 07 12 34 56",
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


def test_backoffice_requires_agency_member(client, agent):
    assert client.get("/agence/").status_code == 302
    client.force_login(agent)
    assert client.get("/agence/").status_code == 200
    assert client.get("/agence/planning/").status_code == 200


@pytest.fixture
def staff(agent):
    return agent


def test_menu_shows_agency_link_to_visitors(client, db):
    html = client.get("/occasions/").content.decode()
    assert 'href="/agence/connexion/"' in html and "Espace agence" in html


def test_dashboard_redirects_to_site_login_page(client, db):
    r = client.get("/agence/")
    assert r.status_code == 302 and r["Location"].startswith("/agence/connexion/?next=/agence/")


def test_staff_login_and_logout(client, staff):
    r = client.post("/agence/connexion/", {"username": "agent", "password": "Secret-123", "next": "/agence/planning/"})
    assert r.status_code == 302 and r["Location"] == "/agence/planning/"
    html = client.get("/agence/").content.decode()
    assert "Déconnexion" in html and "Espace agence" not in html
    assert client.post("/agence/deconnexion/").status_code == 302
    assert client.get("/agence/").status_code == 302


def test_login_defaults_to_dashboard(client, staff):
    r = client.post("/agence/connexion/", {"username": "agent", "password": "Secret-123"})
    assert r["Location"] == "/agence/"


def test_wrong_password_rejected(client, staff):
    r = client.post("/agence/connexion/", {"username": "agent", "password": "nope"})
    assert r.status_code == 200 and "Identifiant ou mot de passe incorrect" in r.content.decode()


def test_user_outside_agency_cannot_log_in(client, db):
    get_user_model().objects.create_user("client", password="Secret-123")
    r = client.post("/agence/connexion/", {"username": "client", "password": "Secret-123"})
    assert r.status_code == 200 and "pas accès" in r.content.decode()
    assert "_auth_user_id" not in client.session


def test_external_next_is_ignored(client, staff):
    r = client.post("/agence/connexion/", {"username": "agent", "password": "Secret-123", "next": "https://evil.example/"})
    assert r["Location"] == "/agence/"


def _web_booking(client, vehicle, t0, **pay):
    fmt = "%Y-%m-%dT%H:%M"
    data = {
        "start": t0.strftime(fmt), "end": (t0 + timedelta(days=2)).strftime(fmt),
        "first_name": "Paul", "last_name": "Obiang", "email": f"paul{len(pay)}@example.com", "phone": "+241 07 00 00 01",
        "birth_date": "1988-02-02", "license_number": "GA1", "license_issued_on": "2010-02-02", **pay,
    }
    return client.post(f"/vehicules/{vehicle.pk}/", data)


def test_cash_booking_through_website(client, vehicle, t0):
    r = _web_booking(client, vehicle, t0, payment_method="cash")
    assert r.status_code == 302
    page = client.get(r["Location"]).content.decode()
    assert "À régler en espèces" in page


def test_mobile_money_requires_number(client, vehicle, t0):
    r = _web_booking(client, vehicle, t0, payment_method="moov")
    assert r.status_code == 200 and "numéro qui recevra" in r.content.decode()


def test_mobile_money_refusal_is_explained(client, vehicle, t0):
    r = _web_booking(client, vehicle, t0, payment_method="airtel", mobile_number="+241 07 00 0000")
    assert r.status_code == 200 and "Paiement refusé" in r.content.decode()
