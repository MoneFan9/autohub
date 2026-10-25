import os
import random
import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Seller
from customers.models import Customer
from payments.services import charge_booking, platform_fee
from rentals import services
from rentals.models import Booking, Extra
from vehicles.models import Agency, Vehicle

VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"

FLEET = [
    # marque, modèle, catégorie, énergie, boîte, places, FCFA/jour, prix de vente FCFA
    ("Hyundai", "i10", "city", "petrol", "manual", 5, 20000, None),
    ("Suzuki", "Swift", "city", "petrol", "manual", 5, 22000, 6500000),
    ("Toyota", "Yaris", "city", "petrol", "auto", 5, 25000, None),
    ("Toyota", "Corolla", "sedan", "petrol", "auto", 5, 35000, 12500000),
    ("Hyundai", "Elantra", "sedan", "petrol", "auto", 5, 35000, None),
    ("Hyundai", "Tucson", "suv", "diesel", "auto", 5, 50000, 16900000),
    ("Toyota", "RAV4", "suv", "petrol", "auto", 5, 55000, None),
    ("Mitsubishi", "Pajero", "suv", "diesel", "manual", 7, 75000, None),
    ("Toyota", "Fortuner", "suv", "diesel", "auto", 7, 80000, None),
    ("Toyota", "Land Cruiser Prado", "premium", "diesel", "auto", 7, 120000, 32000000),
    ("Toyota", "Land Cruiser V8", "premium", "diesel", "auto", 7, 150000, None),
    ("Nissan", "Navara", "pickup", "diesel", "manual", 5, 65000, None),
    ("Toyota", "Hilux", "pickup", "diesel", "manual", 5, 70000, None),
    ("Toyota", "Hiace", "van", "diesel", "manual", 14, 90000, None),
    ("Kia", "Sportage", "suv", "petrol", "auto", 5, None, 9800000),  # particulier, vente uniquement
]

DEMO_DOMAIN = "demo.autohub.ga"
# Vendeurs de démonstration : (identifiant, nom affiché, type, ville, moyens acceptés, lieux, indices FLEET)
SELLERS = [
    ("agent", "Loc'Auto Libreville", "pro", "Libreville", ("airtel", "moov", "card", "cash"),
     [("Aéroport Léon-Mba", "Libreville", "Parking loueurs, aéroport international"), ("Centre-ville", "Libreville", "Boulevard Triomphal")],
     [0, 2, 6, 9, 10, 13]),
    (f"ndong@{DEMO_DOMAIN}", "Garage Ndong Automobiles", "pro", "Port-Gentil", ("airtel", "moov", "cash"),
     [("Garage", "Port-Gentil", "Centre-ville")], [1, 3, 5, 12]),
    (f"mabika@{DEMO_DOMAIN}", "Ets Mabika Location", "pro", "Franceville", ("moov", "cash"),
     [("Agence", "Franceville", "Centre-ville")], [4, 7, 8, 11]),
    (f"marc.ella@{DEMO_DOMAIN}", "Marc E.", "individual", "Libreville", ("airtel", "cash"),
     [("Domicile", "Libreville", "Quartier Louis")], [14]),
]


class Command(BaseCommand):
    help = "Charge un jeu de données de démonstration."

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(7)
        User = get_user_model()
        sellers, vehicle_place = [], {}
        for n, (login, name, kind, city, methods, places, fleet_idx) in enumerate(SELLERS):
            user = self._staff() if login == "agent" else self._demo_user(login, name.split()[0], name.split()[-1])
            seller, _ = Seller.objects.get_or_create(user=user, defaults=dict(
                display_name=name, kind=kind, city=city, phone=f"+241 0{n + 1} 00 00 0{n + 1}",
                whatsapp=f"+241 07 10 00 0{n + 1}", payout_number=f"+241 07 10 00 0{n + 1}",
                **{f"accepts_{m}": m in methods for m in ("airtel", "moov", "card", "cash")},
            ))
            locs = [Agency.objects.get_or_create(seller=seller, name=pname, defaults=dict(city=pcity, address=addr, phone=seller.phone))[0]
                    for pname, pcity, addr in places]
            for k, i in enumerate(fleet_idx):
                vehicle_place[i] = locs[k % len(locs)]
            sellers.append(seller)
        # (code, libellé, FCFA/jour, plafond, description) ; plafond = prix/jour : forfait unique.
        for code, label, price, cap, desc in [
            ("chauffeur", "Avec chauffeur", 25000, None, "Chauffeur professionnel, jusqu'à 10 h par jour"),
            ("province", "Circulation en province", 10000, None, "Pour sortir de la ville de l'agence"),
            ("airport", "Livraison à l'aéroport", 10000, 10000, "Véhicule remis et repris à l'aéroport"),
            ("zero-franchise", "Rachat de franchise", 8000, None, "Réduit la franchise en cas de dommage"),
            ("extra-driver", "Conducteur additionnel", 5000, 40000, ""),
            ("child-seat", "Siège enfant", 3000, 30000, ""),
        ]:
            Extra.objects.get_or_create(code=code, defaults=dict(
                label=label, price_per_day=Decimal(price), max_price=cap and Decimal(cap), description=desc))

        vehicles = []
        for i, (brand, model, cat, fuel, box, seats, rate, sale) in enumerate(FLEET):
            v, _ = Vehicle.objects.get_or_create(
                plate=f"G{chr(65 + i)}-{100 + i * 7}-{chr(90 - i)}{chr(80 - i % 10)}",
                defaults=dict(
                    vin="".join(random.choice(VIN_CHARS) for _ in range(17)), brand=brand, model=model,
                    year=random.choice([2022, 2023, 2024, 2025]), mileage=random.randint(8000, 62000),
                    fuel=fuel, transmission=box, category=cat, seats=seats, agency=vehicle_place[i],
                    is_rentable=rate is not None, daily_rate=rate and Decimal(rate),
                    is_for_sale=sale is not None, sale_price=sale and Decimal(sale),
                    purchase_price=Decimal((rate or 30000) * 330), color=random.choice(["Blanc", "Blanc", "Gris", "Noir"]),
                    description=f"{brand} {model}, climatisation, entretien suivi.",
                ),
            )
            vehicles.append(v)

        if Booking.objects.exists():
            self.stdout.write("Réservations déjà présentes, rien d'autre à faire.")
            return

        names = [("Jean", "Mba Ondo"), ("Christelle", "Nzé Mintsa"), ("Paul", "Obiang"), ("Grâce", "Moussavou"),
                 ("Hervé", "Boussougou"), ("Sylvie", "Ndong"), ("Arnaud", "Mabika"), ("Nadège", "Ella")]
        customers = []
        for i, (f, l) in enumerate(names):
            user = self._demo_user(f"{f.lower()}.{l.lower().replace(' ', '')}@{DEMO_DOMAIN}", f, l)
            customers.append(Customer.objects.create(
                user=user, first_name=f, last_name=l, email=user.email, phone=f"+241 07 00 00 {i:02d}",
                birth_date=date(1985 + i, 3, 10), license_number=f"GA{900000 + i}", license_issued_on=date(2008 + i, 6, 1),
            ))

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
                services.start_rental(b, mileage=vehicles[vi].mileage, fuel_level=100, user=staff, handover_received=True)
            elif final == "cancelled":
                services.cancel_booking(b)
        # Historique : locations terminées (CA sur 30 jours)
        for vi, ci, offset, length in [(6, 3, -20, 5), (11, 4, -15, 3), (13, 5, -12, 7), (2, 6, -9, 4), (9, 7, -25, 10)]:
            total = vehicles[vi].daily_rate * length
            method = random.choice(vehicles[vi].agency.seller.payment_methods)
            b = Booking.objects.create(
                vehicle=vehicles[vi], customer=customers[ci], pickup_agency=vehicles[vi].agency, return_agency=vehicles[vi].agency,
                period=(now + timedelta(days=offset), now + timedelta(days=offset + length)), status=Booking.Status.CONFIRMED,
                days=length, base_amount=total, extras_amount=0, discount_amount=0,
                total_amount=total, deposit_amount=Decimal("100000"), payment_method=method, platform_fee=platform_fee(total),
            )
            if method != "cash":
                charge_booking(b, f"{method}_ok")
            services.start_rental(b, mileage=vehicles[vi].mileage, fuel_level=100, user=staff, handover_received=True)
            Booking.objects.filter(pk=b.pk).update(created_at=now + timedelta(days=offset))
            b.payments.update(created_at=now + timedelta(days=offset))
            services.complete_rental(b, mileage=vehicles[vi].mileage + 120 * length, fuel_level=80, user=staff)
        Vehicle.objects.filter(pk=vehicles[13].pk).update(status=Vehicle.Status.MAINTENANCE)  # Hiace à l'atelier
        self.stdout.write(self.style.SUCCESS("Données de démo chargées."))

    def _book(self, vehicle, customer, start, end, extras):
        b = services.create_booking(vehicle=vehicle, customer=customer, start=start, end=end, extras=extras)
        method = random.choice(vehicle.agency.seller.payment_methods)
        return services.pay_and_confirm(b, services.CASH_TOKEN if method == "cash" else f"{method}_ok")

    def _demo_user(self, email, first, last):
        User = get_user_model()
        user, created = User.objects.get_or_create(username=email, defaults=dict(email=email, first_name=first, last_name=last))
        if created:
            user.set_unusable_password()
            user.save()
        return user

    def _staff(self):
        User = get_user_model()
        user = User.objects.filter(username="agent").first()
        if not user:
            password = os.environ.get("DEMO_AGENT_PASSWORD") or secrets.token_urlsafe(9)
            user = User.objects.create_user("agent", "agent@example.com", password, first_name="Loc'Auto", last_name="Libreville")
            if "DEMO_AGENT_PASSWORD" not in os.environ:
                self.stdout.write(self.style.WARNING(f"Compte agence : agent / {password}"))
        return user
