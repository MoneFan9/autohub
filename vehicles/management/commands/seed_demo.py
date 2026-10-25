import os
import random
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from backoffice.roles import AGENCY_GROUP
from customers.models import Customer
from payments.services import charge_booking
from rentals import services
from rentals.models import Booking, Extra
from vehicles.models import Agency, Vehicle

VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"

FLEET = [
    # marque, modèle, catégorie, énergie, boîte, places, €/jour, prix vente
    ("Renault", "Clio V", "city", "petrol", "manual", 5, 39, None),
    ("Peugeot", "208", "city", "petrol", "auto", 5, 45, 14900),
    ("Fiat", "500e", "city", "electric", "auto", 4, 49, None),
    ("Toyota", "Yaris Hybrid", "city", "hybrid", "auto", 5, 47, None),
    ("Volkswagen", "Golf 8", "sedan", "diesel", "auto", 5, 59, 21500),
    ("Tesla", "Model 3", "sedan", "electric", "auto", 5, 89, None),
    ("Skoda", "Octavia Combi", "sedan", "diesel", "manual", 5, 55, None),
    ("Peugeot", "3008", "suv", "hybrid", "auto", 5, 79, 27900),
    ("Dacia", "Duster", "suv", "petrol", "manual", 5, 49, None),
    ("Kia", "EV6", "suv", "electric", "auto", 5, 99, None),
    ("BMW", "Série 5", "premium", "hybrid", "auto", 5, 139, None),
    ("Mercedes", "Classe C", "premium", "diesel", "auto", 5, 129, 38900),
    ("Renault", "Trafic", "van", "diesel", "manual", 3, 85, None),
    ("Citroën", "Berlingo", "van", "diesel", "manual", 5, 65, None),
]


class Command(BaseCommand):
    help = "Charge un jeu de données de démonstration."

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(7)
        agencies = [
            Agency.objects.get_or_create(name="AutoHub Gare de Lyon", defaults=dict(city="Paris", address="20 bd Diderot, 75012", phone="01 40 00 00 01"))[0],
            Agency.objects.get_or_create(name="AutoHub Part-Dieu", defaults=dict(city="Lyon", address="5 pl. Charles Béraudier, 69003", phone="04 72 00 00 02"))[0],
            Agency.objects.get_or_create(name="AutoHub Saint-Charles", defaults=dict(city="Marseille", address="Square Narvik, 13001", phone="04 91 00 00 03"))[0],
        ]
        for code, label, price, cap in [("gps", "GPS", "5", "35"), ("child-seat", "Siège enfant", "8", "60"),
                                        ("extra-driver", "Conducteur additionnel", "10", "80"), ("zero-franchise", "Rachat de franchise", "15", None)]:
            Extra.objects.get_or_create(code=code, defaults=dict(label=label, price_per_day=Decimal(price), max_price=cap and Decimal(cap)))

        vehicles = []
        for i, (brand, model, cat, fuel, box, seats, rate, sale) in enumerate(FLEET):
            v, _ = Vehicle.objects.get_or_create(
                plate=f"G{chr(65 + i)}-{100 + i * 7}-{chr(90 - i)}{chr(80 - i % 10)}",
                defaults=dict(
                    vin="".join(random.choice(VIN_CHARS) for _ in range(17)), brand=brand, model=model,
                    year=random.choice([2022, 2023, 2024, 2025]), mileage=random.randint(8000, 62000),
                    fuel=fuel, transmission=box, category=cat, seats=seats, agency=agencies[i % 3],
                    daily_rate=Decimal(rate), is_for_sale=sale is not None, sale_price=sale and Decimal(sale),
                    purchase_price=Decimal(rate * 330), color=random.choice(["Gris", "Noir", "Blanc", "Bleu"]),
                    description=f"{brand} {model}, entretien constructeur à jour, Bluetooth, régulateur, climatisation.",
                ),
            )
            vehicles.append(v)

        if Booking.objects.exists():
            self.stdout.write("Réservations déjà présentes, rien d'autre à faire.")
            return

        names = [("Camille", "Martin"), ("Lucas", "Bernard"), ("Inès", "Dubois"), ("Hugo", "Thomas"), ("Léa", "Robert"),
                 ("Nathan", "Petit"), ("Chloé", "Richard"), ("Yanis", "Durand")]
        customers = [Customer.objects.create(
            first_name=f, last_name=l, email=f"{f.lower()}.{l.lower()}@example.com", phone=f"06 00 00 00 {i:02d}",
            birth_date=date(1985 + i, 3, 10), license_number=f"FR{900000 + i}", license_issued_on=date(2008 + i, 6, 1),
        ) for i, (f, l) in enumerate(names)]

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        extras = list(Extra.objects.all())
        plan = [  # véhicule, client, début (j), durée (j), état final
            (0, 0, -3, 6, "active"), (5, 1, -1, 4, "active"), (7, 2, -2, 9, "active"),
            (1, 3, 1, 3, "confirmed"), (4, 4, 0.2, 2, "confirmed"), (10, 5, 2, 5, "confirmed"), (12, 6, 1, 1, "confirmed"),
            (2, 7, 4, 8, "confirmed"), (3, 0, 6, 3, "confirmed"), (9, 1, 8, 12, "confirmed"), (8, 2, 3, 2, "cancelled"),
        ]
        staff = self._staff()
        for vi, ci, offset, length, final in plan:
            start = now + timedelta(days=offset)
            b = self._book(vehicles[vi], customers[ci], start, start + timedelta(days=length), random.sample(extras, k=random.randint(0, 2)))
            if final == "active":
                services.start_rental(b, mileage=vehicles[vi].mileage, fuel_level=100, user=staff)
            elif final == "cancelled":
                services.cancel_booking(b)
        # Historique : locations terminées (CA sur 30 jours)
        for vi, ci, offset, length in [(6, 3, -20, 5), (11, 4, -15, 3), (13, 5, -12, 7), (2, 6, -9, 4), (9, 7, -25, 10)]:
            b = Booking.objects.create(
                vehicle=vehicles[vi], customer=customers[ci], pickup_agency=vehicles[vi].agency, return_agency=vehicles[vi].agency,
                period=(now + timedelta(days=offset), now + timedelta(days=offset + length)), status=Booking.Status.CONFIRMED,
                days=length, base_amount=vehicles[vi].daily_rate * length, extras_amount=0, discount_amount=0,
                total_amount=vehicles[vi].daily_rate * length, deposit_amount=Decimal("300"),
            )
            charge_booking(b, "tok_visa")
            b.payments.update(created_at=now + timedelta(days=offset))
            services.start_rental(b, mileage=vehicles[vi].mileage, fuel_level=100, user=staff)
            services.complete_rental(b, mileage=vehicles[vi].mileage + 120 * length, fuel_level=80, user=staff)
        Vehicle.objects.filter(pk=vehicles[13].pk).update(status=Vehicle.Status.MAINTENANCE)
        self.stdout.write(self.style.SUCCESS("Données de démo chargées."))

    def _book(self, vehicle, customer, start, end, extras):
        b = services.create_booking(vehicle=vehicle, customer=customer, start=start, end=end, extras=extras)
        return services.pay_and_confirm(b, "tok_visa")

    def _staff(self):
        User = get_user_model()
        user = User.objects.filter(username="agent").first()
        if not user:
            password = os.environ.get("DEMO_AGENT_PASSWORD") or secrets.token_urlsafe(9)
            user = User.objects.create_user("agent", "agent@example.com", password)
            user.groups.add(Group.objects.get_or_create(name=AGENCY_GROUP)[0])
            if "DEMO_AGENT_PASSWORD" not in os.environ:
                self.stdout.write(self.style.WARNING(f"Compte agence : agent / {password}"))
        return user
