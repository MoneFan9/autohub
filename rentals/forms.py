from datetime import datetime, time, timedelta

from django import forms
from django.utils import timezone

from customers.models import Customer
from vehicles.models import Agency, Vehicle

from .models import Extra

DT_WIDGET = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


def default_period():
    tomorrow = timezone.localdate() + timedelta(days=1)
    start = timezone.make_aware(datetime.combine(tomorrow, time(10)))
    return start, start + timedelta(days=3)


class PeriodForm(forms.Form):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    start = forms.DateTimeField(label="Départ", widget=DT_WIDGET, input_formats=["%Y-%m-%dT%H:%M"])
    end = forms.DateTimeField(label="Retour", widget=DT_WIDGET, input_formats=["%Y-%m-%dT%H:%M"])

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end:
            if end <= start:
                raise forms.ValidationError("La date de retour doit être après la date de départ.")
            if start < timezone.now() - timedelta(minutes=5):
                raise forms.ValidationError("La date de départ est passée.")
        return data


class SearchForm(PeriodForm):
    city = forms.ChoiceField(label="Ville", required=False)
    category = forms.ChoiceField(label="Catégorie", required=False, choices=[("", "Toutes")] + Vehicle.Category.choices)
    fuel = forms.ChoiceField(label="Énergie", required=False, choices=[("", "Toutes")] + Vehicle.Fuel.choices)
    transmission = forms.ChoiceField(label="Boîte", required=False, choices=[("", "Toutes")] + Vehicle.Transmission.choices)
    max_rate = forms.DecimalField(label="Budget max / jour", required=False, min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cities = Agency.objects.filter(vehicles__isnull=False).values_list("city", flat=True).distinct().order_by("city")
        self.fields["city"].choices = [("", "Toutes les villes")] + [(c, c) for c in cities]


class BookingForm(PeriodForm):
    extras = forms.ModelMultipleChoiceField(
        Extra.objects.all(), required=False, widget=forms.CheckboxSelectMultiple, label="Options", to_field_name="code",
    )
    return_agency = forms.ModelChoiceField(Agency.objects.all(), label="Lieu de retour", required=False, empty_label="Même lieu qu'au départ")
    first_name = forms.CharField(label="Prénom", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    last_name = forms.CharField(label="Nom", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "family-name"}))
    phone = forms.CharField(
        label="Téléphone", max_length=30,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "+241 …"}),
    )
    birth_date = forms.DateField(label="Date de naissance", widget=forms.DateInput(attrs={"type": "date", "autocomplete": "bday"}))
    license_number = forms.CharField(label="Numéro de permis", max_length=30)
    license_issued_on = forms.DateField(label="Permis obtenu le", widget=forms.DateInput(attrs={"type": "date"}))
    payment_method = forms.ChoiceField(
        label="Moyen de paiement", widget=forms.RadioSelect, initial="airtel",
        choices=[("airtel", "Airtel Money"), ("moov", "Moov Money"), ("card", "Carte bancaire"), ("cash", "Espèces, à la remise des clés")],
    )
    mobile_number = forms.CharField(
        label="Numéro Mobile Money", max_length=20, required=False,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "+241 …"}),
        help_text="Vous recevrez une demande de paiement à valider avec votre code secret. Exemple : un numéro finissant par 0000 simule un refus.",
    )
    card_number = forms.CharField(
        label="Numéro de carte", max_length=19, required=False,
        widget=forms.TextInput(attrs={"autocomplete": "cc-number", "inputmode": "numeric"}),
        help_text="Exemple : 4000 0000 0000 0002 simule un refus.",
    )

    CUSTOMER_FIELDS = ["first_name", "last_name", "phone", "birth_date", "license_number", "license_issued_on"]
    METHOD_LABELS = dict(payment_method.choices)

    def __init__(self, *args, methods=None, seller=None, **kwargs):
        super().__init__(*args, **kwargs)
        if seller is not None:
            self.fields["return_agency"].queryset = seller.locations.all()
        if methods:
            # Seuls les moyens acceptés par ce loueur sont proposés.
            self.fields["payment_method"].choices = [(m, self.METHOD_LABELS[m]) for m in ("airtel", "moov", "card", "cash") if m in methods]
            self.fields["payment_method"].initial = self.fields["payment_method"].choices[0][0]

    def customer_data(self):
        return {f: self.cleaned_data[f] for f in self.CUSTOMER_FIELDS}

    def clean(self):
        data = super().clean()
        method = data.get("payment_method")
        if method in ("airtel", "moov") and not self._digits("mobile_number"):
            self.add_error("mobile_number", "Indiquez le numéro qui recevra la demande de paiement.")
        if method == "card" and len(self._digits("card_number")) < 12:
            self.add_error("card_number", "Indiquez un numéro de carte complet.")
        return data

    def _digits(self, field):
        return "".join(c for c in (self.cleaned_data.get(field) or "") if c.isdigit())

    def payment_token(self):
        """Jeton transmis au fournisseur de paiement (simulation tant qu'aucun agrégateur n'est branché)."""
        method = self.cleaned_data["payment_method"]
        if method == "cash":
            return "cash_ok"
        if method == "card":
            declined = self._digits("card_number") == "4000000000000002"
        else:
            declined = self._digits("mobile_number").endswith("0000")
        return f"{method}_{'declined' if declined else 'ok'}"


class InspectionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    handover_received = forms.BooleanField(label="Caution reçue (et paiement en espèces le cas échéant)", required=False)

    mileage = forms.IntegerField(label="Km", min_value=0)
    fuel_level = forms.IntegerField(label="Carburant %", min_value=0, max_value=100, initial=100)
    damages = forms.CharField(label="Dommages", required=False, widget=forms.TextInput(attrs={"placeholder": "Aucun"}))
