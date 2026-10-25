"""Deux rôles, et seulement deux :

- Agence : le personnel des agences (location et vente). Groupe « Agence ». Accès à l'espace agence, jamais à l'admin.
- Propriétaire : le superutilisateur. Seul à accéder à l'admin Django ; a aussi accès à l'espace agence.
"""
from django.contrib.auth.decorators import user_passes_test
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
    """Remplace AdminSite.has_permission : l'admin est réservé au propriétaire."""
    return is_owner(request.user)
