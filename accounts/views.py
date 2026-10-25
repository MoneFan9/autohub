from base64 import b32encode

import segno
from django import forms
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from backoffice.roles import is_seller, owner_required
from rentals import services
from rentals.models import Booking

from .forms import LocationForm, LoginForm, SellerForm, SignupForm


class MemberLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse("backoffice:dashboard") if is_seller(self.request.user) else reverse("accounts:home")


def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Bienvenue sur AutoHub, votre compte est créé.")
        nxt = request.GET.get("next") or request.POST.get("next")
        from django.utils.http import url_has_allowed_host_and_scheme

        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)
        return redirect("accounts:home")
    return render(request, "accounts/signup.html", {"form": form, "next": request.GET.get("next", "")})


@login_required
def home(request):
    bookings = (Booking.objects.filter(customer__user=request.user)
                .select_related("vehicle__agency__seller", "pickup_agency").order_by("-created_at"))
    return render(request, "accounts/home.html", {"bookings": bookings, "now": timezone.now()})


@login_required
@require_POST
def cancel(request, reference):
    booking = get_object_or_404(Booking, reference=reference, customer__user=request.user)
    if booking.start <= timezone.now():
        messages.error(request, "Cette location a déjà commencé : contactez le loueur.")
    else:
        try:
            services.cancel_booking(booking)
            messages.success(request, f"Réservation {booking.reference} annulée.")
        except services.BookingError as exc:
            messages.error(request, str(exc))
    return redirect("accounts:home")


@login_required
@transaction.atomic
def become_seller(request):
    if is_seller(request.user) and not request.user.is_superuser:
        return redirect("backoffice:dashboard")
    form = SellerForm(request.POST or None, prefix="s")
    location = LocationForm(request.POST or None, prefix="l")
    if request.method == "POST" and form.is_valid() and location.is_valid():
        seller = form.save(commit=False)
        seller.user = request.user
        seller.save()
        place = location.save(commit=False)
        place.seller = seller
        place.save()
        messages.success(request, "Profil vendeur créé. Ajoutez maintenant votre premier véhicule.")
        return redirect("backoffice:vehicle_new")
    return render(request, "accounts/become_seller.html", {"form": form, "location": location})


class MemberPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:home")

    def form_valid(self, form):
        messages.success(self.request, "Mot de passe modifié.")
        return super().form_valid(form)


password_change = login_required(MemberPasswordChangeView.as_view())


class TokenForm(forms.Form):
    token = forms.CharField(
        label="Code à 6 chiffres", max_length=6, min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "pattern": "[0-9]{6}"}),
    )


@owner_required
def security(request):
    """Activation de la double authentification du propriétaire (obligatoire pour l'admin)."""
    user = request.user
    if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        return render(request, "accounts/security.html", {"active": True})
    # Le premier appareil s'enregistre ici ; ensuite, seul l'admin (déjà vérifié) peut en gérer d'autres.
    device, _ = TOTPDevice.objects.get_or_create(user=user, confirmed=False, defaults={"name": "Application d'authentification"})
    form = TokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            otp_login(request, device)
            messages.success(request, "Double authentification activée. L'admin vous demandera désormais un code.")
            return redirect("admin:index")
        form.add_error("token", "Code incorrect ou expiré. Saisissez le code affiché en ce moment dans l'application.")
    qr = segno.make(device.config_url, error="m").svg_inline(scale=5, border=2, dark="#0f172a")
    secret = b32encode(device.bin_key).decode().rstrip("=")
    return render(request, "accounts/security.html", {"form": form, "qr": qr, "secret": secret})
