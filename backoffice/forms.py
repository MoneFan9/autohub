from django import forms

from vehicles.models import Vehicle


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "brand", "model", "year", "category", "fuel", "transmission", "seats", "color", "mileage", "plate",
            "description", "video_url", "agency", "status", "is_rentable", "daily_rate", "is_for_sale", "sale_price",
        ]
        labels = {
            "agency": "Lieu de remise", "status": "Disponibilité", "is_rentable": "Je le propose à la location",
            "daily_rate": "Prix par jour (FCFA)", "is_for_sale": "Je le mets en vente", "sale_price": "Prix de vente (FCFA)",
            "plate": "Immatriculation", "mileage": "Kilométrage",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, seller=None, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        if seller is not None:
            self.fields["agency"].queryset = seller.locations.all()
        self.fields["agency"].empty_label = None
        self.fields["status"].choices = [c for c in Vehicle.Status.choices if c[0] != Vehicle.Status.RENTED]

    def clean(self):
        data = super().clean()
        if not data.get("is_rentable") and not data.get("is_for_sale"):
            raise forms.ValidationError("Proposez le véhicule à la location, à la vente, ou les deux.")
        if data.get("is_rentable") and not data.get("daily_rate"):
            self.add_error("daily_rate", "Indiquez le prix par jour.")
        if data.get("is_for_sale") and not data.get("sale_price"):
            self.add_error("sale_price", "Indiquez le prix de vente.")
        return data


class BlockForm(forms.Form):
    start = forms.DateTimeField(label="Du", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), input_formats=["%Y-%m-%dT%H:%M"])
    end = forms.DateTimeField(label="Au", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), input_formats=["%Y-%m-%dT%H:%M"])
    reason = forms.CharField(label="Motif (pour vous)", max_length=120, required=False, widget=forms.TextInput(attrs={"placeholder": "Voyage, usage personnel…"}))

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
