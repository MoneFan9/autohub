import re

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from psycopg.types.range import Range

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
        blocked = VehicleBlock.objects.filter(period__overlap=Range(start, end, "[)")).values("vehicle_id")
        return self.rentable().exclude(id__in=busy).exclude(id__in=blocked)


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
    video_url = models.URLField(
        "vidéo de présentation", blank=True,
        help_text="Lien YouTube, Facebook ou TikTok (facultatif). Faites le tour du véhicule, moteur en marche.",
    )

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

    @property
    def cover(self):
        """Première photo (ordre choisi par le vendeur), ou None : la silhouette dessinée prend le relais."""
        photos = list(self.photos.all())
        return photos[0] if photos else None

    @property
    def youtube_id(self):
        m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})", self.video_url or "")
        return m.group(1) if m else ""


def photo_path(instance, filename):
    return f"vehicules/{instance.vehicle_id}/{filename}"


class VehiclePhoto(models.Model):
    """Photos d'un véhicule : l'acheteur ou le loueur doit pouvoir faire le tour de la voiture, dedans comme dehors."""

    class Kind(models.TextChoices):
        FRONT = "front", "Avant (3/4 avant)"
        REAR = "rear", "Arrière (3/4 arrière)"
        LEFT = "left", "Côté gauche"
        RIGHT = "right", "Côté droit"
        DASHBOARD = "dashboard", "Tableau de bord et compteur"
        FRONT_SEATS = "front_seats", "Sièges avant"
        REAR_SEATS = "rear_seats", "Sièges arrière"
        TRUNK = "trunk", "Coffre"
        ENGINE = "engine", "Moteur"
        TYRES = "tyres", "Pneus et jantes"
        DAMAGE = "damage", "Défaut ou rayure"
        OTHER = "other", "Autre"

    # Vues conseillées, dans l'ordre où on les montre.
    RECOMMENDED = [Kind.FRONT, Kind.REAR, Kind.LEFT, Kind.RIGHT, Kind.DASHBOARD, Kind.FRONT_SEATS, Kind.REAR_SEATS, Kind.TRUNK]

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="photos", verbose_name="véhicule")
    image = models.ImageField("photo", upload_to=photo_path, max_length=500)
    kind = models.CharField("vue", max_length=12, choices=Kind.choices, default=Kind.OTHER)
    position = models.PositiveSmallIntegerField("ordre", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "photo"
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.vehicle.title} · {self.get_kind_display()}"


class VehicleBlock(models.Model):
    """Période où le propriétaire n'est pas disponible (usage personnel, voyage, entretien prévu…)."""

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="blocks", verbose_name="véhicule")
    period = DateTimeRangeField("période")
    reason = models.CharField("motif", max_length=120, blank=True)

    class Meta:
        verbose_name = "indisponibilité"
        ordering = ["period"]
        constraints = [
            ExclusionConstraint(
                name="no_overlapping_blocks",
                expressions=[("vehicle", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
            )
        ]

    def __str__(self):
        return f"{self.vehicle.title} indisponible"

    @property
    def start(self):
        return self.period.lower

    @property
    def end(self):
        return self.period.upper


class Report(models.Model):
    """Signalement d'une annonce par un visiteur (arnaque, véhicule inexistant, contenu inapproprié…)."""

    class Reason(models.TextChoices):
        SCAM = "scam", "Arnaque ou demande de paiement suspecte"
        FAKE = "fake", "Véhicule inexistant ou photos trompeuses"
        WRONG = "wrong", "Informations fausses (prix, kilométrage…)"
        OFFENSIVE = "offensive", "Contenu choquant ou illégal"
        OTHER = "other", "Autre"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="reports", verbose_name="véhicule")
    reason = models.CharField("motif", max_length=12, choices=Reason.choices)
    message = models.TextField("précisions", blank=True, max_length=1000)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="signalé par")
    contact = models.CharField("contact", max_length=120, blank=True)
    handled = models.BooleanField("traité", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "signalement"
        ordering = ["handled", "-created_at"]

    def __str__(self):
        return f"{self.vehicle.title} · {self.get_reason_display()}"



class StoredFile(models.Model):
    """Fichier (photo) conservé en base quand aucun stockage objet n'est configuré : zéro configuration."""

    name = models.CharField(max_length=255, unique=True)
    content = models.BinaryField()
    content_type = models.CharField(max_length=60, default="image/jpeg")
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "fichier stocké"
