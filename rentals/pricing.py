import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

# Remise dégressive selon la durée : (jours minimum, taux)
DURATION_DISCOUNTS = [(30, Decimal("0.25")), (7, Decimal("0.10")), (3, Decimal("0.05"))]
MIN_DEPOSIT = Decimal("300")
DEPOSIT_DAYS = 3


@dataclass(frozen=True)
class Quote:
    days: int
    base_amount: Decimal
    extras_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    deposit_amount: Decimal


def rental_days(start, end):
    if end <= start:
        raise ValueError("La date de retour doit être après la date de départ.")
    return max(1, math.ceil((end - start).total_seconds() / 86400))


def discount_rate(days):
    for threshold, rate in DURATION_DISCOUNTS:
        if days >= threshold:
            return rate
    return Decimal("0")


def quote(vehicle, start, end, extras=()):
    days = rental_days(start, end)
    base = vehicle.daily_rate * days
    extras_total = Decimal("0")
    for extra in extras:
        price = extra.price_per_day * days
        if extra.max_price is not None:
            price = min(price, extra.max_price)
        extras_total += price
    discount = (base * discount_rate(days)).quantize(CENT, ROUND_HALF_UP)
    deposit = max(MIN_DEPOSIT, vehicle.daily_rate * DEPOSIT_DAYS)
    return Quote(
        days=days,
        base_amount=base.quantize(CENT),
        extras_amount=extras_total.quantize(CENT),
        discount_amount=discount,
        total_amount=(base + extras_total - discount).quantize(CENT),
        deposit_amount=deposit.quantize(CENT),
    )
