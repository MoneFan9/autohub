from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_otp.plugins.otp_totp.models import TOTPDevice
from psycopg.types.range import Range

from accounts.forms import LocationForm, SellerForm
from rentals import services
from rentals.forms import InspectionForm
from rentals.models import Booking
from vehicles import services as vehicle_services
from vehicles.models import Vehicle, VehicleBlock, VehiclePhoto

from .forms import BlockForm, VehicleForm
from .roles import is_owner, scope_bookings, scope_vehicles, seller_of, seller_required

EARNING = [Booking.Status.CONFIRMED, Booking.Status.ACTIVE, Booking.Status.COMPLETED]


def _sum(qs, field):
    return qs.aggregate(s=Sum(field))["s"] or Decimal("0")


@seller_required
def dashboard(request):
    now = timezone.now()
    today_end = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    bookings = scope_bookings(Booking.objects.select_related("vehicle", "customer", "pickup_agency", "return_agency"), request.user)

    fleet = scope_vehicles(Vehicle.objects.exclude(status=Vehicle.Status.SOLD), request.user)
    fleet_by_status = dict(fleet.values_list("status").annotate(n=Count("id")))
    rentable_count = fleet.filter(is_rentable=True).count()
    busy_now = bookings.blocking().filter(period__contains=now).values("vehicle").distinct().count()

    recent = bookings.filter(status__in=EARNING, created_at__gte=now - timedelta(days=30))
    gross, fees = _sum(recent, "total_amount"), _sum(recent, "platform_fee")
    cash = recent.filter(payment_method="cash")
    context = {
        "kpis": {
            "fleet": fleet.count(),
            "occupancy": round(100 * busy_now / rentable_count) if rentable_count else 0,
            "net_30d": gross - fees,
            "fees_30d": fees,
            # Espèces : le loueur a encaissé, il doit la commission. En ligne : la plateforme lui doit le net.
            "fees_due": _sum(cash, "platform_fee"),
            "to_pay_out": _sum(recent.exclude(payment_method="cash"), "total_amount") - _sum(recent.exclude(payment_method="cash"), "platform_fee"),
            "active": bookings.filter(status=Booking.Status.ACTIVE).count(),
            "for_sale": fleet.filter(is_for_sale=True).count(),
        },
        "is_platform_view": is_owner(request.user) and seller_of(request.user) is None,
        "fleet_by_status": [(label, fleet_by_status.get(value, 0)) for value, label in Vehicle.Status.choices if value != "sold"],
        "departures": bookings.filter(status=Booking.Status.CONFIRMED, period__startswith__lte=today_end + timedelta(days=2)).order_by("period"),
        "returns": bookings.filter(status=Booking.Status.ACTIVE).order_by("period__endswith"),
        "recent": bookings.order_by("-created_at")[:8],
        "needs_2fa": is_owner(request.user) and not TOTPDevice.objects.filter(user=request.user, confirmed=True).exists(),
        "pickup_form": InspectionForm(),
        "return_form": InspectionForm(),
    }
    return render(request, "backoffice/dashboard.html", context)


def _run(request, reference, fn, needs_inspection=True, with_cash=False):
    booking = get_object_or_404(scope_bookings(Booking.objects.all(), request.user), reference=reference)
    kwargs = {} if needs_inspection else {"by": request.user}
    if needs_inspection:
        form = InspectionForm(request.POST)
        if not form.is_valid():
            messages.error(request, f"{booking.reference} : état des lieux incomplet.")
            return redirect("backoffice:dashboard")
        kwargs = {**form.cleaned_data, "user": request.user}
        if not with_cash:
            kwargs.pop("handover_received")
    try:
        fn(booking, **kwargs)
        messages.success(request, f"{booking.reference} : {booking.get_status_display().lower()}.")
    except services.BookingError as exc:
        messages.error(request, f"{booking.reference} : {exc}")
    return redirect("backoffice:dashboard")


@seller_required
@require_POST
def start_rental(request, reference):
    return _run(request, reference, services.start_rental, with_cash=True)


@seller_required
@require_POST
def complete_rental(request, reference):
    return _run(request, reference, services.complete_rental)


@seller_required
@require_POST
def cancel_booking(request, reference):
    return _run(request, reference, services.cancel_booking, needs_inspection=False)


@seller_required
def planning(request):
    """Planning de flotte sur 14 jours (une ligne par véhicule)."""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [start + timedelta(days=i) for i in range(14)]
    end = days[-1] + timedelta(days=1)
    vehicles = list(scope_vehicles(Vehicle.objects.rentable(), request.user).select_related("agency").order_by("agency__city", "brand"))
    bookings = scope_bookings(Booking.objects.blocking(), request.user).filter(period__overlap=Range(start, end, "[)")).select_related("customer")
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


@seller_required
def vehicles(request):
    qs = scope_vehicles(Vehicle.objects.select_related("agency"), request.user).order_by("brand", "model")
    return render(request, "backoffice/vehicles.html", {"vehicles": qs})


@seller_required
def vehicle_edit(request, pk=None):
    seller = seller_of(request.user)
    if seller is None:
        messages.error(request, "Créez d'abord un profil vendeur pour publier des véhicules.")
        return redirect("accounts:become_seller")
    vehicle = get_object_or_404(scope_vehicles(Vehicle.objects.all(), request.user), pk=pk) if pk else None
    form = VehicleForm(request.POST or None, instance=vehicle, seller=seller)
    if request.method == "POST" and form.is_valid():
        v = form.save()
        if pk:
            messages.success(request, f"{v.title} mis à jour.")
            return redirect("backoffice:vehicles")
        messages.success(request, f"{v.title} publié. Ajoutez maintenant les photos : c'est ce qui décide les clients.")
        return redirect(f"{reverse('backoffice:vehicle_edit', args=[v.pk])}#photos")
    ctx = {"form": form, "vehicle": vehicle, "has_locations": seller.locations.exists()}
    if vehicle:
        ctx.update({
            "photos": vehicle.photos.all(), "kinds": VehiclePhoto.Kind.choices, "missing": vehicle_services.missing_views(vehicle),
            "uploads_enabled": settings.MEDIA_UPLOADS_ENABLED, "max_photos": settings.VEHICLE_MAX_PHOTOS,
            "blocks": vehicle.blocks.filter(period__endswith__gte=timezone.now()), "block_form": BlockForm(),
        })
    return render(request, "backoffice/vehicle_form.html", ctx)


def _own_vehicle(request, pk):
    return get_object_or_404(scope_vehicles(Vehicle.objects.all(), request.user), pk=pk)


def _back(vehicle, anchor):
    return redirect(f"{reverse('backoffice:vehicle_edit', args=[vehicle.pk])}#{anchor}")


@seller_required
@require_POST
def photo_upload(request, pk):
    vehicle = _own_vehicle(request, pk)
    files = request.FILES.getlist("images")
    added, errors = [], []
    for f in files:
        try:
            added.append(vehicle_services.add_photo(vehicle, f, request.POST.get("kind", "other")))
        except vehicle_services.VehicleError as exc:
            errors.append(f"{f.name} : {exc}")
    if request.headers.get("x-requested-with") == "fetch":
        return JsonResponse({"added": len(added), "errors": errors}, status=200 if added or not errors else 400)
    if added:
        messages.success(request, f"{len(added)} photo{'s' if len(added) > 1 else ''} ajoutée{'s' if len(added) > 1 else ''}.")
    for e in errors or ([] if files else ["Choisissez au moins une photo."]):
        messages.error(request, e)
    return _back(vehicle, "photos")


@seller_required
@require_POST
def photo_action(request, pk, photo_id):
    vehicle = _own_vehicle(request, pk)
    photo = get_object_or_404(VehiclePhoto, pk=photo_id, vehicle=vehicle)
    action = request.POST.get("action")
    if action == "delete":
        vehicle_services.delete_photo(photo)
    elif action in ("up", "down", "cover"):
        vehicle_services.move_photo(photo, action)
    elif action == "kind" and request.POST.get("kind") in VehiclePhoto.Kind.values:
        photo.kind = request.POST["kind"]
        photo.save(update_fields=["kind"])
    return _back(vehicle, "photos")


@seller_required
@require_POST
def block_add(request, pk):
    vehicle = _own_vehicle(request, pk)
    form = BlockForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            vehicle_services.block_period(vehicle, d["start"], d["end"], d["reason"])
            messages.success(request, "Indisponibilité enregistrée : le véhicule n'apparaît plus dans les recherches sur cette période.")
        except vehicle_services.VehicleError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Indiquez une date de début et de fin.")
    return _back(vehicle, "dispo")


@seller_required
@require_POST
def block_delete(request, pk, block_id):
    vehicle = _own_vehicle(request, pk)
    get_object_or_404(VehicleBlock, pk=block_id, vehicle=vehicle).delete()
    return _back(vehicle, "dispo")


@seller_required
def profile(request):
    seller = seller_of(request.user)
    if seller is None:
        return redirect("accounts:become_seller")
    form = SellerForm(request.POST or None, instance=seller, prefix="s")
    location = LocationForm(request.POST or None, prefix="l") if "add_location" in request.POST else LocationForm(prefix="l")
    if request.method == "POST":
        if "add_location" in request.POST and location.is_valid():
            place = location.save(commit=False)
            place.seller = seller
            place.save()
            messages.success(request, f"Lieu « {place.name} » ajouté.")
            return redirect("backoffice:profile")
        if "save_profile" in request.POST and form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("backoffice:profile")
    return render(request, "backoffice/profile.html", {"form": form, "location": location, "locations": seller.locations.all()})
