from django.urls import path

from . import views

app_name = "backoffice"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("planning/", views.planning, name="planning"),
    path("agenda/<uuid:token>.ics", views.calendar_feed, name="calendar_feed"),
    path("agenda/nouveau-lien/", views.calendar_reset, name="calendar_reset"),
    path("reservations/<str:reference>/", views.booking_detail, name="booking"),
    path("vehicules/", views.vehicles, name="vehicles"),
    path("vehicules/nouveau/", views.vehicle_edit, name="vehicle_new"),
    path("vehicules/<int:pk>/modifier/", views.vehicle_edit, name="vehicle_edit"),
    path("vehicules/<int:pk>/photos/", views.photo_upload, name="photo_upload"),
    path("vehicules/<int:pk>/photos/<int:photo_id>/", views.photo_action, name="photo_action"),
    path("vehicules/<int:pk>/indisponibilites/", views.block_add, name="block_add"),
    path("vehicules/<int:pk>/indisponibilites/<int:block_id>/supprimer/", views.block_delete, name="block_delete"),
    path("profil/", views.profile, name="profile"),
    path("reservations/<str:reference>/depart/", views.start_rental, name="start"),
    path("reservations/<str:reference>/retour/", views.complete_rental, name="complete"),
    path("reservations/<str:reference>/annuler/", views.cancel_booking, name="cancel"),
]
