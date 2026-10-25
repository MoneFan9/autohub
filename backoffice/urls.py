from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "backoffice"
urlpatterns = [
    path("connexion/", views.AgencyLoginView.as_view(), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("mot-de-passe/", views.agency_password_change, name="password"),
    path("securite/", views.security, name="security"),
    path("", views.dashboard, name="dashboard"),
    path("planning/", views.planning, name="planning"),
    path("reservations/<str:reference>/depart/", views.start_rental, name="start"),
    path("reservations/<str:reference>/retour/", views.complete_rental, name="complete"),
    path("reservations/<str:reference>/annuler/", views.cancel_booking, name="cancel"),
]
