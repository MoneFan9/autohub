"""Planning : frise, navigation, indisponibilités, fiche réservation, flux d'agenda."""
from datetime import timedelta

from django.utils import timezone

from backoffice.planning import build_rows
from rentals import services
from vehicles import services as vehicle_services

from .conftest import make_seller

D = timedelta(days=1)


def midnight(days=0):
    d = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))


def test_booking_becomes_one_segment(vehicle, customer):
    b = services.create_booking(vehicle=vehicle, customer=customer, start=midnight(2) + timedelta(hours=10), end=midnight(5) + timedelta(hours=10))
    row = build_rows([vehicle], [b], [], timezone.localdate(), 7)[0]
    kinds = [(s["kind"], s["span"]) for s in row["segments"]]
    # jours 0-1 libres, réservation du jour 2 au jour 5 inclus (retour à 10 h), jour 6 libre
    assert kinds == [("free", 1), ("free", 1), ("booking", 4), ("free", 1)]
    assert sum(s["span"] for s in row["segments"]) == 7


def test_planning_page_navigation_and_links(client, agent, vehicle, customer):
    b = services.create_booking(vehicle=vehicle, customer=customer, start=midnight(1) + timedelta(hours=9), end=midnight(3) + timedelta(hours=9))
    vehicle_services.block_period(vehicle, midnight(5), midnight(6), "Voyage")
    client.force_login(agent)
    html = client.get("/espace-vendeur/planning/?jours=7").content.decode()
    assert f'href="/espace-vendeur/reservations/{b.reference}/"' in html and "Voyage" in html
    assert f"?bloquer={(timezone.localdate()).isoformat()}" in html
    nxt = (timezone.localdate() + timedelta(days=7)).isoformat()
    assert f"?debut={nxt}&jours=7" in html
    assert client.get("/espace-vendeur/planning/?debut=nimporte&jours=99").status_code == 200


def test_free_day_prefills_block_form(client, agent, vehicle):
    client.force_login(agent)
    day = (timezone.localdate() + timedelta(days=4)).isoformat()
    html = client.get(f"/espace-vendeur/vehicules/{vehicle.pk}/modifier/?bloquer={day}").content.decode()
    assert f'value="{day}T00:00"' in html


def test_booking_detail_and_scoping(client, agent, vehicle, customer):
    b = services.pay_and_confirm(services.create_booking(vehicle=vehicle, customer=customer, start=midnight(1), end=midnight(2)), services.CASH_TOKEN)
    client.force_login(agent)
    page = client.get(f"/espace-vendeur/reservations/{b.reference}/").content.decode()
    assert "Remise des clés" in page and customer.phone in page and "FR1" in page
    r = client.post(f"/espace-vendeur/reservations/{b.reference}/depart/",
                    {"mileage": 10, "fuel_level": 100, "handover_received": "on", "next": f"/espace-vendeur/reservations/{b.reference}/"})
    assert r["Location"] == f"/espace-vendeur/reservations/{b.reference}/"
    client.force_login(make_seller("autre"))
    assert client.get(f"/espace-vendeur/reservations/{b.reference}/").status_code == 404


def test_calendar_feed(client, agent, vehicle, customer):
    b = services.create_booking(vehicle=vehicle, customer=customer, start=midnight(1), end=midnight(2))
    token = agent.seller.calendar_token
    r = client.get(f"/espace-vendeur/agenda/{token}.ics")
    body = r.content.decode()
    assert r["Content-Type"].startswith("text/calendar") and body.startswith("BEGIN:VCALENDAR")
    assert f"UID:{b.reference}@autohub" in body and "Renault Clio" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    client.force_login(agent)
    client.post("/espace-vendeur/agenda/nouveau-lien/")
    agent.seller.refresh_from_db()
    assert agent.seller.calendar_token != token
    assert client.get(f"/espace-vendeur/agenda/{token}.ics").status_code == 404
