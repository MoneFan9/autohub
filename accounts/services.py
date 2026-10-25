from datetime import date

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rentals.models import Booking

from .models import TermsAcceptance

OPEN = [Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.ACTIVE]


class AccountError(Exception):
    pass


def record_acceptance(user, document):
    TermsAcceptance.objects.create(user=user, document=document, version=settings.TERMS_VERSION)


@transaction.atomic
def delete_account(user):
    """Droit à l'effacement : données personnelles anonymisées, historique comptable des locations conservé."""
    seller = getattr(user, "seller", None)
    open_bookings = Booking.objects.filter(status__in=OPEN, period__endswith__gte=timezone.now())
    if open_bookings.filter(customer__user=user).exists() or (seller and open_bookings.filter(vehicle__agency__seller=seller).exists()):
        raise AccountError("Des réservations sont en cours ou à venir : annulez-les ou attendez leur fin avant de supprimer le compte.")
    customer = getattr(user, "customer", None)
    if customer:
        customer.first_name, customer.last_name = "Compte", "supprimé"
        customer.email = customer.phone = ""
        customer.license_number = "—"
        customer.birth_date = customer.license_issued_on = date(1900, 1, 1)
        customer.user = None
        customer.save()
    if seller:
        from vehicles.models import Vehicle, VehiclePhoto

        vehicles = Vehicle.objects.filter(agency__seller=seller)
        for photo in VehiclePhoto.objects.filter(vehicle__in=vehicles):
            photo.image.delete(save=False)
            photo.delete()
        vehicles.update(is_rentable=False, is_for_sale=False, status=Vehicle.Status.SOLD, description="", video_url="")
        seller.display_name, seller.phone, seller.whatsapp, seller.payout_number = "Compte supprimé", "", "", ""
        seller.save()
    user.username = f"supprime-{user.pk}"
    user.email = user.first_name = user.last_name = ""
    user.is_active = False
    user.set_unusable_password()
    user.save()
