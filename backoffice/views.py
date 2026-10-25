from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from base64 import b32encode

import segno
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.urls import reverse_lazy
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from psycopg.types.range import Range

from payments.models import Payment
from payments.services import total_revenue
from rentals import services
from rentals.forms import InspectionForm
from rentals.models import Booking
from vehicles.models import Vehicle

from .roles import agency_required, is_agency_member, is_owner, owner_required



class AgencyAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Identifiant ou mot de passe incorrect.",
        "not_staff": "Ce compte n'a pas accès à l'espace agence.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not is_agency_member(user):
            raise forms.ValidationError(self.error_messages["not_staff"], code="not_staff")


class AgencyLoginView(LoginView):
    template_name = "backoffice/login.html"
    authentication_form = AgencyAuthenticationForm
    redirect_authenticated_user = True


class AgencyPasswordChangeView(PasswordChangeView):
    template_name = "backoffice/password_change.html"
    success_url = reverse_lazy("backoffice:dashboard")

    def form_valid(self, form):
        messages.success(self.request, "Mot de passe modifié.")
        return super().form_valid(form)


agency_password_change = agency_required(AgencyPasswordChangeView.as_view())


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
        return render(request, "backoffice/security.html", {"active": True})
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
    return render(request, "backoffice/security.html", {"form": form, "qr": qr, "secret": secret})


@agency_required
def dashboard(request):
    now = timezone.now()
    today_end = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    bookings = Booking.objects.select_related("vehicle", "customer", "pickup_agency", "return_agency")

    fleet = Vehicle.objects.exclude(status=Vehicle.Status.SOLD)
    fleet_by_status = dict(fleet.values_list("status").annotate(n=Count("id")))
    rentable_count = fleet.filter(is_rentable=True).count()
    busy_now = Booking.objects.blocking().filter(period__contains=now).values("vehicle").distinct().count()

    month = Payment.objects.filter(created_at__gte=now - timedelta(days=30))
    context = {
        "kpis": {
            "fleet": fleet.count(),
            "occupancy": round(100 * busy_now / rentable_count) if rentable_count else 0,
            "revenue_30d": total_revenue(month),
            "active": bookings.filter(status=Booking.Status.ACTIVE).count(),
            "for_sale": Vehicle.objects.for_sale().count(),
        },
        "fleet_by_status": [(label, fleet_by_status.get(value, 0)) for value, label in Vehicle.Status.choices if value != "sold"],
        "departures": bookings.filter(status=Booking.Status.CONFIRMED, period__startswith__lte=today_end + timedelta(days=2)).order_by("period"),
        "returns": bookings.filter(status=Booking.Status.ACTIVE).order_by("period__endswith"),
        "recent": bookings.order_by("-created_at")[:8],
        "needs_2fa": is_owner(request.user) and not TOTPDevice.objects.filter(user=request.user, confirmed=True).exists(),
        "pickup_form": InspectionForm(),
        "return_form": InspectionForm(),
    }
    return render(request, "backoffice/dashboard.html", context)


def _run(request, reference, fn, needs_inspection=True):
    booking = get_object_or_404(Booking, reference=reference)
    kwargs = {}
    if needs_inspection:
        form = InspectionForm(request.POST)
        if not form.is_valid():
            messages.error(request, f"{booking.reference} : état des lieux incomplet.")
            return redirect("backoffice:dashboard")
        kwargs = {**form.cleaned_data, "user": request.user}
    try:
        fn(booking, **kwargs)
        messages.success(request, f"{booking.reference} : {booking.get_status_display().lower()}.")
    except services.BookingError as exc:
        messages.error(request, f"{booking.reference} : {exc}")
    return redirect("backoffice:dashboard")


@agency_required
@require_POST
def start_rental(request, reference):
    return _run(request, reference, services.start_rental)


@agency_required
@require_POST
def complete_rental(request, reference):
    return _run(request, reference, services.complete_rental)


@agency_required
@require_POST
def cancel_booking(request, reference):
    return _run(request, reference, services.cancel_booking, needs_inspection=False)


@agency_required
def planning(request):
    """Planning de flotte sur 14 jours (une ligne par véhicule)."""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [start + timedelta(days=i) for i in range(14)]
    end = days[-1] + timedelta(days=1)
    vehicles = list(Vehicle.objects.rentable().select_related("agency").order_by("agency__city", "brand"))
    bookings = Booking.objects.blocking().filter(period__overlap=Range(start, end, "[)")).select_related("customer")
    by_vehicle = {}
    for b in bookings:
        by_vehicle.setdefault(b.vehicle_id, []).append(b)
    rows = []
    for v in vehicles:
        cells = []
        for d in days:
            d_end = d + timedelta(days=1)
            hit = next((b for b in by_vehicle.get(v.id, []) if b.start < d_end and b.end > d), None)
            cells.append(hit)
        rows.append((v, cells))
    return render(request, "backoffice/planning.html", {"days": days, "rows": rows})
