from django.urls import path

from . import views

app_name = "backoffice"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("planning/", views.planning, name="planning"),
    path("vehicules/", views.vehicles, name="vehicles"),
    path("vehicules/nouveau/", views.vehicle_edit, name="vehicle_new"),
    path("vehicules/<int:pk>/modifier/", views.vehicle_edit, name="vehicle_edit"),
    path("profil/", views.profile, name="profile"),
    path("reservations/<str:reference>/depart/", views.start_rental, name="start"),
    path("reservations/<str:reference>/retour/", views.complete_rental, name="complete"),
    path("reservations/<str:reference>/annuler/", views.cancel_booking, name="cancel"),
]
