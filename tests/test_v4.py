"""Lancement en espèces : gratuit (aucune commission) et paiements en ligne grisés."""
from datetime import timedelta
from decimal import Decimal

import pytest

from accounts.models import Seller
from rentals import services


@pytest.fixture
def cash_only(settings):
    settings.ONLINE_PAYMENTS = "off"
    settings.FEES_ACTIVE = False


def test_no_commission_in_cash_mode(cash_only, vehicle, customer, t0):
    b = services.pay_and_confirm(services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + timedelta(days=2)), services.CASH_TOKEN)
    assert b.platform_fee == Decimal("0")


def test_commission_hidden_everywhere_in_cash_mode(cash_only, client, agent, vehicle):
    for url in ("/", "/infos/cgu/", "/compte/devenir-vendeur/"):
        html = client.get(url).content.decode()
        assert "% de commission" not in html and "prélève" not in html, url
    assert "aucune commission" in client.get("/infos/cgu/").content.decode()
    client.force_login(agent)
    for url in ("/espace-vendeur/", f"/espace-vendeur/vehicules/{vehicle.pk}/modifier/"):
        html = client.get(url).content.decode()
        assert "Commission" not in html and "prélève" not in html, url


def test_seller_form_forces_cash_in_cash_mode(cash_only, client, member):
    client.force_login(member)
    html = client.get("/compte/devenir-vendeur/").content.decode()
    assert "Bientôt disponible" in html
    assert 'name="s-accepts_airtel" disabled' in html and 'name="s-accepts_cash" disabled id="id_s-accepts_cash" checked' in html
    # Même en forçant les cases, seules les espèces sont enregistrées.
    client.post("/compte/devenir-vendeur/", {
        "s-display_name": "Awa", "s-kind": "individual", "s-city": "Libreville", "s-phone": "077",
        "s-accepts_airtel": "on", "s-accepts_card": "on", "s-accept_terms": "on",
        "l-name": "Domicile", "l-city": "Libreville", "l-address": "Louis",
    })
    seller = Seller.objects.get(display_name="Awa")
    assert (seller.accepts_cash, seller.accepts_airtel, seller.accepts_card) == (True, False, False)
    assert seller.payment_methods == ["cash"]


def test_cta_and_booking_copy_in_cash_mode(cash_only, client, vehicle):
    assert "en espèces au propriétaire" in client.get("/").content.decode()
