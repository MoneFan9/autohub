"""Deux rôles, et seulement deux :

- Agence : le personnel des agences (location et vente). Groupe « Agence ». Accès à l'espace agence, jamais à l'admin.
- Propriétaire : le superutilisateur. Seul à accéder à l'admin Django ; a aussi accès à l'espace agence.
"""
from django.contrib.auth.decorators import user_passes_test
from django_otp import devices_for_user
from django_otp.admin import OTPAdminAuthenticationForm
from rest_framework.permissions import BasePermission

AGENCY_GROUP = "Agence"


def is_owner(user):
    return user.is_active and user.is_superuser


def is_agency_member(user):
    if not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or user.groups.filter(name=AGENCY_GROUP).exists()


agency_required = user_passes_test(is_agency_member, login_url="backoffice:login")


class IsAgencyMember(BasePermission):
    def has_permission(self, request, view):
        return is_agency_member(request.user)


def owner_only_admin(request):
    """Remplace AdminSite.has_permission : l'admin est réservé au propriétaire, après double authentification."""
    return is_owner(request.user) and request.user.is_verified()


owner_required = user_passes_test(is_owner, login_url="backoffice:login")


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
