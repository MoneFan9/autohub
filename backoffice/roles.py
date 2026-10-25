"""Trois rôles sur la place de marché :

- Client : tout membre inscrit. Il loue, suit et annule ses réservations (espace « Mon compte »).
- Vendeur / loueur : membre qui a créé un profil vendeur. Il gère SES véhicules et SES réservations, jamais ceux des autres.
- Propriétaire de la plateforme : le superutilisateur. Seul à accéder à l'admin (avec double authentification) ;
  voit l'ensemble de l'activité et les commissions.
"""
from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect
from django_otp import devices_for_user
from django_otp.admin import OTPAdminAuthenticationForm
from rest_framework.permissions import BasePermission


def is_owner(user):
    return user.is_active and user.is_superuser


def seller_of(user):
    if not user.is_authenticated:
        return None
    return getattr(user, "seller", None)


def is_seller(user):
    """Accès à l'espace vendeur : un profil vendeur, ou le propriétaire de la plateforme."""
    return user.is_authenticated and user.is_active and (user.is_superuser or seller_of(user) is not None)


def seller_required(view):
    """Non connecté : page de connexion. Connecté sans profil vendeur : création du profil."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_seller(request.user):
            return redirect("accounts:become_seller")
        return view(request, *args, **kwargs)

    return wrapper


def scope_bookings(qs, user):
    """Le propriétaire voit tout ; un vendeur ne voit que les réservations de ses véhicules."""
    return qs if user.is_superuser else qs.filter(vehicle__agency__seller=seller_of(user))


def scope_vehicles(qs, user):
    return qs if user.is_superuser else qs.filter(agency__seller=seller_of(user))


class IsSeller(BasePermission):
    def has_permission(self, request, view):
        return is_seller(request.user)


def owner_only_admin(request):
    """Remplace AdminSite.has_permission : l'admin est réservé au propriétaire, après double authentification."""
    return is_owner(request.user) and request.user.is_verified()


owner_required = user_passes_test(is_owner, login_url="accounts:login")


class OwnerAdminLoginForm(OTPAdminAuthenticationForm):
    """Connexion admin : mot de passe + code. Si le compte n'a qu'un appareil, inutile de le choisir."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["otp_token"].label = "Code à 6 chiffres (application d'authentification)"
        self.fields["otp_token"].widget.attrs.update({"inputmode": "numeric", "autocomplete": "one-time-code"})

    def _chosen_device(self, user):
        device = super()._chosen_device(user)
        if device is None:
            confirmed = list(devices_for_user(user, confirmed=True))
            if len(confirmed) == 1:
                device = confirmed[0]
        return device
