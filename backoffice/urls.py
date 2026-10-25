from django.urls import path

from . import views

app_name = "backoffice"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("planning/", views.planning, name="planning"),
    path("reservations/<str:reference>/depart/", views.start_rental, name="start"),
    path("reservations/<str:reference>/retour/", views.complete_rental, name="complete"),
    path("reservations/<str:reference>/annuler/", views.cancel_booking, name="cancel"),
]
