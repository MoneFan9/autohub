import secrets

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q
from psycopg.types.range import Range


class Extra(models.Model):
    code = models.SlugField(unique=True)
    label = models.CharField("libellé", max_length=80)
    price_per_day = models.DecimalField("prix / jour", max_digits=10, decimal_places=2)
    max_price = models.DecimalField("plafond", max_digits=12, decimal_places=2, null=True, blank=True)
    description = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name = "option"

    def __str__(self):
        return self.label


class BookingQuerySet(models.QuerySet):
    def blocking(self):
        return self.filter(status__in=Booking.BLOCKING_STATUSES)

    def overlapping(self, start, end):
        return self.filter(period__overlap=Range(start, end, "[)"))


def _new_reference():
    return "AH-" + secrets.token_hex(4).upper()


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente de paiement"
        CONFIRMED = "confirmed", "Confirmée"
        ACTIVE = "active", "En cours"
        COMPLETED = "completed", "Terminée"
        CANCELLED = "cancelled", "Annulée"

    BLOCKING_STATUSES = [Status.PENDING, Status.CONFIRMED, Status.ACTIVE]

    reference = models.CharField("référence", max_length=12, unique=True, default=_new_reference, editable=False)
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="bookings", verbose_name="véhicule")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="bookings", verbose_name="client")
    pickup_agency = models.ForeignKey("vehicles.Agency", on_delete=models.PROTECT, related_name="+", verbose_name="agence de départ")
    return_agency = models.ForeignKey("vehicles.Agency", on_delete=models.PROTECT, related_name="+", verbose_name="agence de retour")
    period = DateTimeRangeField("période")
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.PENDING)
    extras = models.ManyToManyField(Extra, blank=True, verbose_name="options")

    days = models.PositiveSmallIntegerField("jours")
    base_amount = models.DecimalField("location", max_digits=10, decimal_places=2)
    extras_amount = models.DecimalField("options", max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField("remise", max_digits=10, decimal_places=2)
    total_amount = models.DecimalField("total TTC", max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField("caution", max_digits=10, decimal_places=2)
    payment_method = models.CharField("moyen de paiement", max_length=10, blank=True)
    platform_fee = models.DecimalField("commission plateforme", max_digits=10, decimal_places=2, default=0)
    reminder_sent_at = models.DateTimeField("rappel envoyé le", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        verbose_name = "réservation"
        ordering = ["-created_at"]
        constraints = [
            # Garantie au niveau base : deux réservations actives ne peuvent pas se chevaucher.
            ExclusionConstraint(
                name="no_overlapping_bookings",
                expressions=[("vehicle", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
                condition=Q(status__in=["pending", "confirmed", "active"]),
            ),
        ]

    def __str__(self):
        return self.reference

    @property
    def seller(self):
        return self.vehicle.agency.seller

    PAYMENT_LABELS = {"airtel": "Airtel Money", "moov": "Moov Money", "card": "Carte", "cash": "Espèces"}

    @property
    def payment_label(self):
        return self.PAYMENT_LABELS.get(self.payment_method, "—")

    @property
    def seller_amount(self):
        return self.total_amount - self.platform_fee

    @property
    def balance_due(self):
        from payments.services import balance_due

        return balance_due(self)

    @property
    def start(self):
        return self.period.lower

    @property
    def end(self):
        return self.period.upper


class Inspection(models.Model):
    class Kind(models.TextChoices):
        PICKUP = "pickup", "Départ"
        RETURN = "return", "Retour"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="inspections")
    kind = models.CharField(max_length=6, choices=Kind.choices)
    mileage = models.PositiveIntegerField("kilométrage")
    fuel_level = models.PositiveSmallIntegerField("niveau carburant / batterie (%)", validators=[MaxValueValidator(100)])
    damages = models.TextField("dommages constatés", blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "état des lieux"
        verbose_name_plural = "états des lieux"
        constraints = [models.UniqueConstraint(fields=["booking", "kind"], name="one_inspection_per_kind")]
