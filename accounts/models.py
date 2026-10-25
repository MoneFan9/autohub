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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vendeur / loueur"
        verbose_name_plural = "vendeurs / loueurs"
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name

    @property
    def payment_methods(self):
        methods = [("airtel", self.accepts_airtel), ("moov", self.accepts_moov), ("card", self.accepts_card), ("cash", self.accepts_cash)]
        return [m for m, ok in methods if ok]
