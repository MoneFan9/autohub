from datetime import date

from django.db import models


class Customer(models.Model):
    user = models.OneToOneField("auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="customer")
    first_name = models.CharField("prénom", max_length=80)
    last_name = models.CharField("nom", max_length=80)
    email = models.EmailField(db_index=True)
    phone = models.CharField("téléphone", max_length=30)
    birth_date = models.DateField("date de naissance")
    license_number = models.CharField("n° de permis", max_length=30)
    license_issued_on = models.DateField("permis obtenu le")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "client"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @staticmethod
    def _years_since(d, today):
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))

    def age(self, today=None):
        return self._years_since(self.birth_date, today or date.today())

    def license_years(self, today=None):
        return self._years_since(self.license_issued_on, today or date.today())
