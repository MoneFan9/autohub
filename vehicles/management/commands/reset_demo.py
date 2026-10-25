from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from customers.models import Customer
from payments.models import Payment
from rentals.models import Booking, Extra, Inspection
from vehicles.models import Agency, Vehicle


class Command(BaseCommand):
    help = "Efface toutes les données métier (agences, flotte, clients, réservations, paiements) et recharge la démo. Les comptes sont conservés."

    def add_arguments(self, parser):
        parser.add_argument("--oui", action="store_true", help="Confirme l'effacement.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts["oui"]:
            raise CommandError("Effacement non confirmé : relancez avec --oui.")
        for model in (Payment, Inspection, Booking, Customer, Vehicle, Agency, Extra):
            model.objects.all().delete()
        call_command("seed_demo")
