import uuid

from django.conf import settings
from django.db import models


class Seller(models.Model):
    """Membre qui publie des véhicules à louer et/ou à vendre. La plateforme ne possède aucun véhicule."""

    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", "Particulier"
        PRO = "pro", "Professionnel"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller")
    display_name = models.CharField("nom affiché", max_length=80)
    kind = models.CharField("type", max_length=12, choices=Kind.choices, default=Kind.INDIVIDUAL)
    city = models.CharField("ville", max_length=80)
    phone = models.CharField("téléphone", max_length=30)
    whatsapp = models.CharField("WhatsApp", max_length=30, blank=True)

    # Moyens de paiement que ce vendeur accepte de ses clients.
    accepts_airtel = models.BooleanField("Airtel Money", default=True)
    accepts_moov = models.BooleanField("Moov Money", default=True)
    accepts_card = models.BooleanField("carte bancaire", default=False)
    accepts_cash = models.BooleanField("espèces", default=True)
    payout_number = models.CharField(
        "numéro de versement Mobile Money", max_length=30, blank=True,
        help_text="Où la plateforme vous reverse les paiements en ligne, commission déduite.",
    )
    # Lien secret de l'agenda (abonnement depuis Google Agenda, iPhone…) ; régénérable.
    calendar_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vendeur / loueur"
        verbose_name_plural = "vendeurs / loueurs"
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name

    @property
    def payment_methods(self):
        if settings.ONLINE_PAYMENTS == "off":
            # Sans paiement en ligne, tout se règle à la remise des clés.
            return ["cash"]
        methods = [("airtel", self.accepts_airtel), ("moov", self.accepts_moov), ("card", self.accepts_card), ("cash", self.accepts_cash)]
        return [m for m, ok in methods if ok]

    LABELS = {"airtel": "Airtel Money", "moov": "Moov Money", "card": "carte", "cash": "espèces"}

    @property
    def payment_labels(self):
        return [self.LABELS[m] for m in self.payment_methods]

    @property
    def whatsapp_link(self):
        digits = "".join(c for c in (self.whatsapp or "") if c.isdigit())
        return f"https://wa.me/{digits}" if digits else ""


class TermsAcceptance(models.Model):
    """Trace de l'acceptation des conditions (preuve en cas de litige)."""

    class Document(models.TextChoices):
        TERMS = "terms", "Conditions générales d'utilisation et confidentialité"
        SELLER = "seller", "Engagements du loueur / vendeur"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="acceptances")
    document = models.CharField(max_length=10, choices=Document.choices)
    version = models.CharField(max_length=20)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "acceptation des conditions"
        verbose_name_plural = "acceptations des conditions"
