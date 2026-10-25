from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from customers.models import Customer
from rentals.models import Extra
from vehicles.models import Agency, Vehicle


@pytest.fixture
def agency(db):
    return Agency.objects.create(name="Gare", city="Paris", address="1 rue X")


@pytest.fixture
def vehicle(agency):
    return Vehicle.objects.create(
        vin="VF1RJA00012345678", plate="AA-123-BB", brand="Renault", model="Clio", year=2024,
        fuel="petrol", transmission="manual", category="city", agency=agency, daily_rate=Decimal("40"),
    )


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
