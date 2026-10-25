from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

vin_validator = RegexValidator(r"^[A-HJ-NPR-Z0-9]{17}$", "VIN invalide (17 caractères, sans I, O, Q).")


class Agency(models.Model):
    """Lieu de remise des clés d'un vendeur (agence, domicile, parking…)."""

    seller = models.ForeignKey("accounts.Seller", on_delete=models.CASCADE, related_name="locations", null=True, blank=True, verbose_name="vendeur")
    name = models.CharField("nom", max_length=100)
    city = models.CharField("ville", max_length=100)
    address = models.CharField("adresse", max_length=255)
    phone = models.CharField("téléphone", max_length=30, blank=True)

    class Meta:
        verbose_name = "lieu de remise"
        verbose_name_plural = "lieux de remise"
        ordering = ["city", "name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class VehicleQuerySet(models.QuerySet):
    def rentable(self):
        return self.filter(is_rentable=True).exclude(
            status__in=[Vehicle.Status.MAINTENANCE, Vehicle.Status.SOLD]
        )

    def for_sale(self):
        return self.filter(is_for_sale=True).exclude(status=Vehicle.Status.SOLD)

    def available_between(self, start, end):
        from rentals.models import Booking

        busy = Booking.objects.blocking().overlapping(start, end).values("vehicle_id")
        return self.rentable().exclude(id__in=busy)


class Vehicle(models.Model):
    class Fuel(models.TextChoices):
        PETROL = "petrol", "Essence"
        DIESEL = "diesel", "Diesel"
        HYBRID = "hybrid", "Hybride"
        ELECTRIC = "electric", "Électrique"

    class Transmission(models.TextChoices):
        MANUAL = "manual", "Manuelle"
        AUTO = "auto", "Automatique"

    class Category(models.TextChoices):
        CITY = "city", "Citadine"
        SEDAN = "sedan", "Berline"
        SUV = "suv", "SUV / 4x4"
        PICKUP = "pickup", "Pick-up"
        VAN = "van", "Minibus / utilitaire"
        PREMIUM = "premium", "Premium"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        RENTED = "rented", "En location"
        MAINTENANCE = "maintenance", "Atelier"
        SOLD = "sold", "Vendu"

    vin = models.CharField("VIN", max_length=17, unique=True, null=True, blank=True, validators=[vin_validator])
    plate = models.CharField("immatriculation", max_length=12, unique=True)
    brand = models.CharField("marque", max_length=50)
    model = models.CharField("modèle", max_length=80)
    year = models.PositiveSmallIntegerField("année", validators=[MinValueValidator(1990)])
    mileage = models.PositiveIntegerField("kilométrage", default=0)
    fuel = models.CharField("énergie", max_length=10, choices=Fuel.choices)
    transmission = models.CharField("boîte", max_length=10, choices=Transmission.choices)
    category = models.CharField("catégorie", max_length=10, choices=Category.choices)
    seats = models.PositiveSmallIntegerField("places", default=5)
    color = models.CharField("couleur", max_length=30, blank=True)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="vehicles/", blank=True)

    agency = models.ForeignKey(Agency, on_delete=models.PROTECT, related_name="vehicles", verbose_name="agence")
    status = models.CharField("statut", max_length=12, choices=Status.choices, default=Status.AVAILABLE)

    # Un même véhicule peut être loué puis mis en vente : c'est le cœur du modèle.
    is_rentable = models.BooleanField("proposé à la location", default=True)
    is_for_sale = models.BooleanField("proposé à la vente", default=False)
    daily_rate = models.DecimalField("tarif / jour", max_digits=8, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField("prix de vente", max_digits=10, decimal_places=2, null=True, blank=True)
    purchase_price = models.DecimalField("prix d'achat", max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = VehicleQuerySet.as_manager()

    class Meta:
        verbose_name = "véhicule"
        ordering = ["brand", "model"]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_rentable=False) | Q(daily_rate__isnull=False),
                name="rentable_requires_daily_rate",
            ),
            models.CheckConstraint(
                condition=Q(is_for_sale=False) | Q(sale_price__isnull=False),
                name="for_sale_requires_price",
            ),
        ]

    def __str__(self):
        return f"{self.brand} {self.model} ({self.plate})"

    @property
    def seller(self):
        return self.agency.seller

    @property
    def title(self):
        return f"{self.brand} {self.model}"
