from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django.contrib.auth import get_user_model

from accounts.models import Seller
from customers.models import Customer
from payments.models import Payment
from rentals.models import Booking, Extra, Inspection
from vehicles.models import Agency, Vehicle

from .seed_demo import DEMO_DOMAIN


class Command(BaseCommand):
    help = "Efface toutes les données métier (vendeurs, lieux, flotte, clients, réservations, paiements) et les comptes de démo, puis recharge la démo. Les autres comptes sont conservés."

    def add_arguments(self, parser):
        parser.add_argument("--oui", action="store_true", help="Confirme l'effacement.")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts["oui"]:
            raise CommandError("Effacement non confirmé : relancez avec --oui.")
        for model in (Payment, Inspection, Booking, Customer, Vehicle, Agency, Extra, Seller):
            model.objects.all().delete()
        get_user_model().objects.filter(username__endswith="@" + DEMO_DOMAIN).delete()
        call_command("seed_demo")
