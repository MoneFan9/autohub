from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from vehicles.models import Agency

from .models import Seller

User = get_user_model()


class SignupForm(UserCreationForm):
    accept_terms = forms.BooleanField(
        label="J'accepte les conditions générales d'utilisation et la politique de confidentialité",
        error_messages={"required": "Acceptez les conditions pour créer votre compte."},
    )
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

    accept_terms = forms.BooleanField(
        label="Je certifie avoir le droit de louer ou vendre ces véhicules, qu'ils sont assurés et en règle, et j'accepte les engagements du loueur / vendeur",
        error_messages={"required": "Ces engagements sont obligatoires pour publier des véhicules."},
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["accept_terms"]
        self.online_open = settings.ONLINE_PAYMENTS != "off"
        if not self.online_open:
            # Paiement en ligne pas encore ouvert : grisé ; espèces imposées (seul moyen possible).
            for name in ("accepts_airtel", "accepts_moov", "accepts_card"):
                self.fields[name].disabled = True
                self.initial[name] = False
            self.fields["accepts_cash"].disabled = True
            self.initial["accepts_cash"] = True
            self.fields["payout_number"].disabled = True

    def clean(self):
        data = super().clean()
        if not self.online_open:
            return data
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


class DeleteAccountForm(forms.Form):
    password = forms.CharField(label="Votre mot de passe", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, user, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data["password"]):
            raise forms.ValidationError("Mot de passe incorrect.")
        return self.cleaned_data["password"]
