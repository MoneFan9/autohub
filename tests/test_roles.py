"""Agence = personnel qui loue et vend. Admin = le propriétaire seul."""
from django.contrib.auth import get_user_model

from backoffice.roles import is_agency_member, is_owner

from .conftest import make_agency_member


def test_agency_member_uses_agency_space_but_never_admin(client, agent):
    client.force_login(agent)
    assert client.get("/agence/").status_code == 200
    assert client.get("/agence/planning/").status_code == 200
    r = client.get("/admin/")
    assert r.status_code == 302 and r["Location"].startswith("/admin/login/")
    assert client.get("/admin/rentals/booking/").status_code == 302


def test_agency_member_cannot_log_into_admin(client, agent):
    r = client.post("/admin/login/", {"username": "agent", "password": "Secret-123", "next": "/admin/"})
    assert r.status_code == 200  # formulaire réaffiché, pas de redirection vers l'admin
    assert client.get("/admin/").status_code == 302


def test_staff_flag_alone_does_not_open_admin(client, db):
    # Même si quelqu'un coche « statut équipe » sur un compte, l'admin reste fermé hors propriétaire.
    user = make_agency_member("chef", is_staff=True)
    client.force_login(user)
    assert client.get("/admin/").status_code == 302


def test_owner_has_admin_and_agency_space(client, owner):
    client.force_login(owner)
    assert client.get("/admin/").status_code == 200
    assert client.get("/agence/").status_code == 200


def test_menu_shows_admin_link_to_owner_only(client, agent, owner):
    client.force_login(agent)
    html = client.get("/agence/").content.decode()
    assert "Tableau de bord" in html and 'href="/admin/"' not in html
    client.force_login(owner)
    assert 'href="/admin/"' in client.get("/agence/").content.decode()


def test_agency_can_operate_rentals_via_api(client, agent):
    from rest_framework.test import APIClient

    api = APIClient()
    api.force_authenticate(agent)
    assert api.get("/api/bookings/").status_code == 200


def test_role_helpers(db, agent, owner):
    outsider = get_user_model().objects.create_user("client")
    assert is_agency_member(agent) and not is_owner(agent)
    assert is_agency_member(owner) and is_owner(owner)
    assert not is_agency_member(outsider) and not is_owner(outsider)


def test_demo_seed_creates_agent_as_agency_member_not_superuser(db, monkeypatch):
    from django.core.management import call_command

    monkeypatch.setenv("DEMO_AGENT_PASSWORD", "x-demo-pass")
    call_command("seed_demo", verbosity=0)
    agent = get_user_model().objects.get(username="agent")
    assert not agent.is_superuser and not agent.is_staff and is_agency_member(agent)


def test_ensure_owner_creates_superuser_once(db, monkeypatch):
    from django.core.management import call_command

    monkeypatch.setenv("OWNER_USERNAME", "patronne")
    monkeypatch.setenv("OWNER_PASSWORD", "Tres-Secret-1")
    call_command("ensure_owner")
    call_command("ensure_owner")
    users = get_user_model().objects.filter(username="patronne")
    assert users.count() == 1 and users.get().is_superuser
