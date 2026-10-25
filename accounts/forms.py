from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from vehicles.models import Agency

from .models import Seller

User = get_user_model()


class SignupForm(UserCreationForm):
    first_name = forms.CharField(label="Prénom", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    last_name = forms.CharField(label="Nom", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "family-name"}))
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].label = "Confirmer le mot de passe"
        self.fields["password1"].help_text = "8 caractères minimum, pas uniquement des chiffres."
        self.fields["password2"].help_text = ""

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(username__iexact=email).exists() or User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet e-mail. Connectez-vous.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "E-mail (ou identifiant) ou mot de passe incorrect.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail ou identifiant"


class SellerForm(forms.ModelForm):
    class Meta:
        model = Seller
        fields = ["display_name", "kind", "city", "phone", "whatsapp", "accepts_airtel", "accepts_moov", "accepts_card", "accepts_cash", "payout_number"]
        widgets = {
            "kind": forms.RadioSelect,
            "phone": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "+241 …"}),
            "whatsapp": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "+241 …"}),
            "payout_number": forms.TextInput(attrs={"inputmode": "tel", "placeholder": "+241 …"}),
        }
        labels = {"display_name": "Nom affiché aux clients", "whatsapp": "WhatsApp (facultatif)"}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if not any(data.get(f) for f in ("accepts_airtel", "accepts_moov", "accepts_card", "accepts_cash")):
            raise forms.ValidationError("Acceptez au moins un moyen de paiement.")
        if (data.get("accepts_airtel") or data.get("accepts_moov") or data.get("accepts_card")) and not data.get("payout_number"):
            self.add_error("payout_number", "Indiquez le numéro sur lequel vous recevrez les paiements en ligne.")
        return data


class LocationForm(forms.ModelForm):
    class Meta:
        model = Agency
        fields = ["name", "city", "address", "phone"]
        labels = {"name": "Nom du lieu", "address": "Adresse ou repère", "phone": "Téléphone sur place"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "Ex. : Aéroport, domicile, garage…"})}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
