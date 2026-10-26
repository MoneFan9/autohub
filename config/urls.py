from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from rentals.api import BookingViewSet, ExtraViewSet
from pages import views as pages
from pages.sitemaps import SITEMAPS
from vehicles import views
from vehicles.api import AgencyViewSet, VehicleViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("agencies", AgencyViewSet)
router.register("extras", ExtraViewSet)
router.register("bookings", BookingViewSet)

from backoffice.roles import OwnerAdminLoginForm, owner_only_admin  # noqa: E402

admin.site.site_header = "AutoHub — administration"
admin.site.has_permission = owner_only_admin
admin.site.login_form = OwnerAdminLoginForm
admin.site.login_template = "admin/otp_login.html"

urlpatterns = [
    path("", views.home, name="home"),
    path("vehicules/<int:pk>/", views.vehicle_detail, name="vehicle-detail"),
    path("reservation/<str:reference>/", views.booking_confirmation, name="booking-confirmation"),
    path("occasions/", views.used_cars, name="used-cars"),
    path("occasions/<int:pk>/", views.used_car_detail, name="used-car-detail"),
    path("reservation/<str:reference>/paiement/", views.booking_payment, name="booking-payment"),
    path("occasions/<int:pk>/signaler/", views.report_vehicle, name="report-vehicle"),
    path("infos/<slug:slug>/", pages.legal, name="legal"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", pages.robots),
    path("taches/quotidiennes/", pages.daily_tasks),
    path("fichiers/<path:name>", views.stored_file, name="stored-file"),
    path("compte/", include("accounts.urls")),
    path("espace-vendeur/", include("backoffice.urls")),
    # Anciennes adresses de l'espace agence (V1)
    path("agence/", RedirectView.as_view(pattern_name="backoffice:dashboard")),
    path("agence/connexion/", RedirectView.as_view(pattern_name="accounts:login", query_string=True)),
    path("agence/securite/", RedirectView.as_view(pattern_name="accounts:security")),
    path("agence/mot-de-passe/", RedirectView.as_view(pattern_name="accounts:password")),
    path("api/", include((router.urls, "api"))),
    path("admin/", admin.site.urls),
]
