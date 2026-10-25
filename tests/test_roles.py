"""Client = tout membre. Vendeur = membre avec un profil vendeur, limité à ses véhicules. Admin = le propriétaire seul."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from backoffice.roles import is_owner, is_seller
from rentals import services
from vehicles.models import Vehicle

from .conftest import make_member, make_seller


def test_seller_uses_seller_space_but_never_admin(client, agent):
    client.force_login(agent)
    assert client.get("/espace-vendeur/").status_code == 200
    assert client.get("/espace-vendeur/planning/").status_code == 200
    r = client.get("/admin/")
    assert r.status_code == 302 and r["Location"].startswith("/admin/login/")


def test_seller_cannot_log_into_admin(client, agent):
    r = client.post("/admin/login/", {"username": "agent", "password": "Secret-123", "next": "/admin/"})
    assert r.status_code == 200
    assert client.get("/admin/").status_code == 302


def test_staff_flag_alone_does_not_open_admin(client, db):
    client.force_login(make_seller("chef", is_staff=True))
    assert client.get("/admin/").status_code == 302


def test_owner_needs_second_factor_for_admin(client, owner):
    client.force_login(owner)
    assert client.get("/espace-vendeur/").status_code == 200
    assert client.get("/admin/").status_code == 302


def test_menu_shows_admin_link_to_owner_only(client, agent, owner):
    client.force_login(agent)
    html = client.get("/espace-vendeur/").content.decode()
    assert "Espace vendeur" in html and 'href="/admin/"' not in html
    client.force_login(owner)
    html = client.get("/espace-vendeur/").content.decode()
    assert 'href="/admin/"' in html and "Activez la double authentification" in html and "Toute la plateforme" in html


def test_member_without_profile_is_sent_to_become_seller(client, member):
    client.force_login(member)
    r = client.get("/espace-vendeur/")
    assert r.status_code == 302 and r["Location"] == "/compte/devenir-vendeur/"


def test_seller_sees_only_own_bookings_and_vehicles(client, vehicle, customer, t0):
    other = make_seller("autre")
    theirs = Vehicle.objects.create(brand="Toyota", model="Hilux", year=2023, fuel="diesel", transmission="manual",
                                    category="pickup", agency=other.seller.locations.get(), daily_rate=50)
    mine = services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + timedelta(days=1))
    services.create_booking(vehicle=theirs, customer=customer, start=t0, end=t0 + timedelta(days=1))
    client.force_login(other)
    html = client.get("/espace-vendeur/").content.decode()
    assert mine.reference not in html
    assert "Renault Clio" not in client.get("/espace-vendeur/vehicules/").content.decode()
    assert client.get(f"/espace-vendeur/vehicules/{vehicle.pk}/modifier/").status_code == 404
    r = client.post(f"/espace-vendeur/reservations/{mine.reference}/annuler/")
    assert r.status_code == 404
    api = APIClient()
    api.force_authenticate(other)
    assert api.get("/api/bookings/").json()["count"] == 1
    assert api.post(f"/api/bookings/{mine.reference}/cancel/").status_code == 404


def test_role_helpers(db, agent, owner):
    outsider = make_member("client")
    assert is_seller(agent) and not is_owner(agent)
    assert is_seller(owner) and is_owner(owner)
    assert not is_seller(outsider) and not is_owner(outsider)


def test_demo_seed_creates_marketplace_sellers(db, monkeypatch):
    from django.core.management import call_command

    monkeypatch.setenv("DEMO_AGENT_PASSWORD", "x-demo-pass")
    call_command("seed_demo", verbosity=0)
    agent = get_user_model().objects.get(username="agent")
    assert not agent.is_superuser and not agent.is_staff and is_seller(agent)
    from accounts.models import Seller

    assert Seller.objects.count() >= 3 and Seller.objects.filter(kind="individual").exists()


def test_ensure_owner_creates_superuser_once(db, monkeypatch):
    from django.core.management import call_command

    monkeypatch.setenv("OWNER_USERNAME", "patronne")
    monkeypatch.setenv("OWNER_PASSWORD", "Tres-Secret-1")
    call_command("ensure_owner")
    call_command("ensure_owner")
    users = get_user_model().objects.filter(username="patronne")
    assert users.count() == 1 and users.get().is_superuser
