from datetime import timedelta

from accounts.models import Seller
from rentals.models import Booking
from vehicles.models import Vehicle

from .conftest import make_seller

FMT = "%Y-%m-%dT%H:%M"


def test_home_search_lists_vehicle_with_seller(client, vehicle):
    html = client.get("/").content.decode()
    assert "Renault Clio" in html and "par Loueur agent" in html
    assert f'href="/vehicules/{vehicle.pk}/?' in html


def test_home_filters_by_city(client, vehicle):
    assert "Renault Clio" not in client.get("/", {"city": "Franceville"}).content.decode()
    assert "Renault Clio" in client.get("/", {"city": "Libreville"}).content.decode()


def _web_booking(client, vehicle, t0, **pay):
    data = {
        "start": t0.strftime(FMT), "end": (t0 + timedelta(days=2)).strftime(FMT),
        "first_name": "Paul", "last_name": "Obiang", "phone": "+241 07 00 00 01",
        "birth_date": "1988-02-02", "license_number": "GA1", "license_issued_on": "2010-02-02", **pay,
    }
    return client.post(f"/vehicules/{vehicle.pk}/", data)


def test_booking_requires_an_account(client, vehicle, t0):
    r = _web_booking(client, vehicle, t0, payment_method="card", card_number="4242 4242 4242 4242")
    assert r.status_code == 302 and r["Location"] == f"/compte/connexion/?next=/vehicules/{vehicle.pk}/"
    assert not Booking.objects.exists()


def test_mobile_money_request_to_pay_flow(client, member, vehicle, gps, t0):
    client.force_login(member)
    r = _web_booking(client, vehicle, t0, extras=[gps.code], payment_method="airtel", mobile_number="+241 07 12 34 56")
    booking = Booking.objects.get()
    assert r.status_code == 302 and r["Location"] == f"/reservation/{booking.reference}/paiement/"
    assert booking.status == "pending" and booking.customer.user == member
    page = client.get(r["Location"]).content.decode()
    assert "Validez le paiement sur votre téléphone" in page and "+241 07 12 34 56" in page
    r = client.post(r["Location"])
    booking.refresh_from_db()
    assert booking.status == "confirmed" and booking.platform_fee > 0
    assert r["Location"] == f"/reservation/{booking.reference}/"
    assert "confirmée" in client.get(r["Location"]).content.decode()


def test_mobile_money_refusal_cancels_and_frees_vehicle(client, member, vehicle, t0):
    client.force_login(member)
    r = _web_booking(client, vehicle, t0, payment_method="moov", mobile_number="+241 06 00 0000")
    page = client.post(r["Location"]).content.decode()
    assert "Paiement non abouti" in page
    assert Booking.objects.get().status == "cancelled"
    assert Vehicle.objects.available_between(t0, t0 + timedelta(days=2)).exists()


def test_stale_pending_payment_expires(client, member, vehicle, t0):
    client.force_login(member)
    _web_booking(client, vehicle, t0, payment_method="airtel", mobile_number="+241 07 12 34 56")
    Booking.objects.update(created_at=Booking.objects.get().created_at - timedelta(minutes=30))
    client.get("/")
    assert Booking.objects.get().status == "cancelled"


def test_cash_booking_through_website(client, member, vehicle, t0):
    client.force_login(member)
    r = _web_booking(client, vehicle, t0, payment_method="cash")
    assert r.status_code == 302
    page = client.get(r["Location"]).content.decode()
    assert "À régler en espèces" in page and "pièce d'identité" in page


def test_only_seller_methods_are_offered(client, member, t0):
    seller = make_seller("ndong", methods=("moov", "cash"))
    v = Vehicle.objects.create(brand="Toyota", model="Hilux", year=2023, fuel="diesel", transmission="manual",
                               category="pickup", agency=seller.seller.locations.get(), daily_rate=50)
    html = client.get(f"/vehicules/{v.pk}/").content.decode()
    assert "Moov Money" in html and "Airtel Money</span>" not in html and "Carte bancaire" not in html
    client.force_login(member)
    r = _web_booking(client, v, t0, payment_method="card", card_number="4242 4242 4242 4242")
    assert r.status_code == 200 and not Booking.objects.exists()


def test_return_place_must_belong_to_same_seller(client, member, vehicle, t0):
    other = make_seller("autre")
    client.force_login(member)
    r = _web_booking(client, vehicle, t0, payment_method="cash", return_agency=other.seller.locations.get().pk)
    assert r.status_code == 200 and not Booking.objects.exists()


def test_card_refusal_is_explained(client, member, vehicle, t0):
    client.force_login(member)
    r = _web_booking(client, vehicle, t0, payment_method="card", card_number="4000 0000 0000 0002")
    assert r.status_code == 200 and "Paiement refusé" in r.content.decode()


def test_mobile_money_requires_number(client, member, vehicle, t0):
    client.force_login(member)
    r = _web_booking(client, vehicle, t0, payment_method="moov")
    assert r.status_code == 200 and "numéro qui recevra" in r.content.decode()


def test_confirmation_not_visible_to_others(client, vehicle, customer, member, t0):
    from rentals import services

    b = services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + timedelta(days=1))
    assert client.get(f"/reservation/{b.reference}/").status_code == 404
    client.force_login(member)
    assert client.get(f"/reservation/{b.reference}/").status_code == 404


def test_member_sees_and_cancels_own_booking(client, member, vehicle, t0):
    client.force_login(member)
    _web_booking(client, vehicle, t0, payment_method="cash")
    b = Booking.objects.get()
    assert b.reference in client.get("/compte/").content.decode()
    client.post(f"/compte/reservations/{b.reference}/annuler/")
    b.refresh_from_db()
    assert b.status == "cancelled"


def test_signup_then_become_seller_and_publish(client, db):
    r = client.post("/compte/inscription/", {"first_name": "Awa", "last_name": "Mba", "email": "Awa@Example.com",
                                             "password1": "Un-mot-de-passe-1", "password2": "Un-mot-de-passe-1"})
    assert r.status_code == 302 and r["Location"] == "/compte/"
    r = client.post("/compte/devenir-vendeur/", {
        "s-display_name": "Awa M.", "s-kind": "individual", "s-city": "Libreville", "s-phone": "+241 07 11 22 33",
        "s-accepts_cash": "on", "l-name": "Domicile", "l-city": "Libreville", "l-address": "Quartier Louis",
    })
    assert r.status_code == 302 and r["Location"] == "/espace-vendeur/vehicules/nouveau/"
    seller = Seller.objects.get(display_name="Awa M.")
    assert seller.payment_methods == ["cash"]
    r = client.post("/espace-vendeur/vehicules/nouveau/", {
        "brand": "Suzuki", "model": "Swift", "year": 2020, "category": "city", "fuel": "petrol", "transmission": "manual",
        "seats": 5, "mileage": 40000, "plate": "GA-123-AB", "agency": seller.locations.get().pk, "status": "available",
        "is_for_sale": "on", "sale_price": 4500000,
    })
    assert r.status_code == 302, r.context["form"].errors
    v = Vehicle.objects.get(model="Swift")
    page = client.get(f"/occasions/{v.pk}/").content.decode()
    assert "Awa M." in page and "tel:+24107112233" in page


def test_online_methods_need_payout_number(client, member):
    client.force_login(member)
    r = client.post("/compte/devenir-vendeur/", {
        "s-display_name": "X", "s-kind": "pro", "s-city": "Oyem", "s-phone": "1", "s-accepts_airtel": "on",
        "l-name": "Garage", "l-city": "Oyem", "l-address": "Centre",
    })
    assert r.status_code == 200 and "numéro sur lequel vous recevrez" in r.content.decode()


def test_menu_for_visitors(client, db):
    html = client.get("/occasions/").content.decode()
    assert 'href="/compte/connexion/"' in html and "Créer un compte" in html


def test_seller_login_goes_to_seller_space(client, agent, member):
    r = client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123"})
    assert r["Location"] == "/espace-vendeur/"
    client.post("/compte/deconnexion/")
    r = client.post("/compte/connexion/", {"username": "hugo", "password": "Secret-789"})
    assert r["Location"] == "/compte/"


def test_external_next_is_ignored(client, agent):
    r = client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123", "next": "https://evil.example/"})
    assert r["Location"] == "/espace-vendeur/"


def test_wrong_password_rejected(client, agent):
    r = client.post("/compte/connexion/", {"username": "agent", "password": "nope"})
    assert r.status_code == 200 and "mot de passe incorrect" in r.content.decode()


def test_old_agency_urls_redirect(client, db):
    assert client.get("/agence/connexion/")["Location"] == "/compte/connexion/"


def test_departure_requires_handover_checkbox(client, agent, vehicle, customer, t0):
    from rentals import services

    b = services.pay_and_confirm(services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + timedelta(days=1)), services.CASH_TOKEN)
    client.force_login(agent)
    assert "J'ai reçu" in client.get("/espace-vendeur/").content.decode()
    client.post(f"/espace-vendeur/reservations/{b.reference}/depart/", {"mileage": 10, "fuel_level": 100})
    b.refresh_from_db()
    assert b.status == "confirmed"
    client.post(f"/espace-vendeur/reservations/{b.reference}/depart/", {"mileage": 10, "fuel_level": 100, "handover_received": "on"})
    b.refresh_from_db()
    assert b.status == "active" and b.balance_due == 0


def test_returning_member_dates_are_prefilled(client, member, vehicle, t0):
    client.force_login(member)
    _web_booking(client, vehicle, t0, payment_method="cash")
    html = client.get(f"/vehicules/{vehicle.pk}/").content.decode()
    assert 'value="1988-02-02"' in html and 'value="2010-02-02"' in html
