"""E-mails envoyés au client et au loueur. Un échec d'envoi ne bloque jamais une réservation."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

log = logging.getLogger(__name__)


def _send(to, subject, template, context):
    to = [a for a in to if a and "@" in a]
    if not to:
        return
    body = render_to_string(f"emails/{template}.txt", {**context, "site_url": settings.SITE_URL})
    try:
        send_mail(f"{settings.SITE_NAME} · {subject}", body, None, to)
    except Exception:  # noqa: BLE001 - un fournisseur e-mail en panne ne doit pas casser le parcours
        log.exception("E-mail non envoyé : %s", subject)


def _people(booking):
    seller = booking.seller
    customer = booking.customer
    client_email = (customer.user.email if customer.user_id else "") or customer.email
    seller_email = seller.user.email if seller else ""
    return customer, client_email, seller, seller_email


def booking_confirmed(booking):
    customer, client_email, seller, seller_email = _people(booking)
    ctx = {"b": booking, "customer": customer, "seller": seller,
           "dashboard_url": settings.SITE_URL + reverse("backoffice:dashboard"),
           "account_url": settings.SITE_URL + reverse("accounts:home")}
    _send([client_email], f"Réservation {booking.reference} confirmée", "booking_confirmed_client", ctx)
    _send([seller_email], f"Nouvelle réservation {booking.reference}", "booking_confirmed_seller", ctx)


def booking_cancelled(booking, by=None):
    customer, client_email, seller, seller_email = _people(booking)
    ctx = {"b": booking, "customer": customer, "seller": seller, "by_seller": bool(by and seller and by == seller.user)}
    _send([client_email, seller_email], f"Réservation {booking.reference} annulée", "booking_cancelled", ctx)


def departure_reminder(booking):
    customer, client_email, seller, seller_email = _people(booking)
    ctx = {"b": booking, "customer": customer, "seller": seller}
    _send([client_email], "Votre départ approche", "reminder_client", ctx)
    _send([seller_email], f"Remise des clés {booking.reference}", "reminder_seller", ctx)


def vehicle_reported(report):
    owner = settings.CONTACT_EMAIL
    _send([owner], f"Signalement : {report.vehicle.title}", "report", {"r": report,
          "admin_url": settings.SITE_URL + reverse("admin:vehicles_report_change", args=[report.pk])})
