from django.db import models


class Payment(models.Model):
    class Kind(models.TextChoices):
        CHARGE = "charge", "Paiement"
        DEPOSIT_HOLD = "deposit_hold", "Empreinte caution"
        DEPOSIT_RELEASE = "deposit_release", "Libération caution"
        REFUND = "refund", "Remboursement"

    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Réussi"
        FAILED = "failed", "Échoué"

    booking = models.ForeignKey("rentals.Booking", on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.CharField(max_length=20)
    provider_ref = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "paiement"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount} € ({self.booking})"
