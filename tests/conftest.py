from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Seller
from customers.models import Customer
from rentals.models import Extra
from vehicles.models import Agency, Vehicle


def make_seller(username, password=None, methods=("airtel", "moov", "card", "cash"), **extra):
    """Membre avec un profil vendeur et un lieu de remise."""
    user = get_user_model().objects.create_user(username, password=password, **extra)
    seller = Seller.objects.create(
        user=user, display_name=f"Loueur {username}", city="Libreville", phone="+241 01 00 00 00",
        payout_number="+241 07 00 00 00", **{f"accepts_{m}": m in methods for m in ("airtel", "moov", "card", "cash")},
    )
    Agency.objects.create(seller=seller, name=f"Garage {username}", city="Libreville", address="Bd Triomphal")
    return user


def make_member(username, password=None):
    return get_user_model().objects.create_user(username, email=f"{username}@example.com", password=password)


@pytest.fixture
def agent(db):
    return make_seller("agent", password="Secret-123")


@pytest.fixture
def agency(agent):
    return agent.seller.locations.get()


@pytest.fixture
def vehicle(agency):
    return Vehicle.objects.create(
        vin="VF1RJA00012345678", plate="AA-123-BB", brand="Renault", model="Clio", year=2024,
        fuel="petrol", transmission="manual", category="city", agency=agency, daily_rate=Decimal("40"),
    )


@pytest.fixture
def member(db):
    return make_member("hugo", password="Secret-789")


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        first_name="Camille", last_name="Martin", email="camille@example.com", phone="0600000000",
        birth_date=date(1990, 1, 1), license_number="FR1", license_issued_on=date(2010, 1, 1),
    )


@pytest.fixture
def gps(db):
    return Extra.objects.create(code="gps", label="GPS", price_per_day=Decimal("5"), max_price=Decimal("20"))


@pytest.fixture
def t0():
    return (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)


@pytest.fixture
def owner(db):
    return get_user_model().objects.create_superuser("patron", "", "Secret-456")
