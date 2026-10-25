from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from rentals.api import BookingViewSet, ExtraViewSet
from vehicles import views
from vehicles.api import AgencyViewSet, VehicleViewSet

router = DefaultRouter()
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("agencies", AgencyViewSet)
router.register("extras", ExtraViewSet)
router.register("bookings", BookingViewSet)

admin.site.site_header = "AutoHub — administration"

urlpatterns = [
    path("", views.home, name="home"),
    path("vehicules/<int:pk>/", views.vehicle_detail, name="vehicle-detail"),
    path("reservation/<str:reference>/", views.booking_confirmation, name="booking-confirmation"),
    path("occasions/", views.used_cars, name="used-cars"),
    path("agence/", include("backoffice.urls")),
    path("api/", include((router.urls, "api"))),
    path("admin/", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
