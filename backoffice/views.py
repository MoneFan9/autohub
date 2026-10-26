from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.forms import LocationForm, SellerForm
from rentals import services
from rentals.forms import InspectionForm
from rentals.models import Booking
from vehicles import services as vehicle_services
from vehicles.models import Vehicle, VehicleBlock, VehiclePhoto

from . import planning as planning_tools
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


def _back_to(request):
    """Retour à la page d'origine (fiche réservation, planning) ou au tableau de bord."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("backoffice:dashboard")


def _run(request, reference, fn, needs_inspection=True, with_cash=False):
    booking = get_object_or_404(scope_bookings(Booking.objects.all(), request.user), reference=reference)
    kwargs = {} if needs_inspection else {"by": request.user}
    if needs_inspection:
        form = InspectionForm(request.POST)
        if not form.is_valid():
            messages.error(request, f"{booking.reference} : état des lieux incomplet.")
            return _back_to(request)
        kwargs = {**form.cleaned_data, "user": request.user}
        if not with_cash:
            kwargs.pop("handover_received")
    try:
        fn(booking, **kwargs)
        messages.success(request, f"{booking.reference} : {booking.get_status_display().lower()}.")
    except services.BookingError as exc:
        messages.error(request, f"{booking.reference} : {exc}")
    return _back_to(request)


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
    """Frise de la flotte : navigation par période, réservations et indisponibilités cliquables."""
    first, span = planning_tools.parse_window(request.GET)
    vehicles = list(scope_vehicles(Vehicle.objects.rentable(), request.user).select_related("agency").order_by("agency__city", "brand"))
    bookings, blocks = planning_tools.window_queries(scope_bookings(Booking.objects.all(), request.user), vehicles, first, span)
    days = [first + timedelta(days=i) for i in range(span)]
    seller = seller_of(request.user)
    ctx = {
        "days": days, "span": span, "spans": planning_tools.SPANS, "first": first, "today": timezone.localdate(),
        "rows": planning_tools.build_rows(vehicles, bookings, blocks, first, span),
        "prev": first - timedelta(days=span), "next": first + timedelta(days=span), "last": days[-1],
        "feed_url": settings.SITE_URL + reverse("backoffice:calendar_feed", args=[seller.calendar_token]) if seller else "",
    }
    return render(request, "backoffice/planning.html", ctx)


@seller_required
def booking_detail(request, reference):
    booking = get_object_or_404(
        scope_bookings(Booking.objects.select_related("vehicle__agency", "customer", "pickup_agency", "return_agency"), request.user),
        reference=reference,
    )
    return render(request, "backoffice/booking_detail.html", {
        "b": booking, "inspections": booking.inspections.all(), "payments": booking.payments.order_by("created_at"),
    })


def calendar_feed(request, token):
    """Flux iCalendar public mais secret (le jeton fait office de mot de passe)."""
    from django.http import HttpResponse

    from accounts.models import Seller

    seller = get_object_or_404(Seller, calendar_token=token)
    response = HttpResponse(planning_tools.ical(seller, settings.SITE_URL), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="autohub.ics"'
    response["Cache-Control"] = "private, max-age=900"
    return response


@seller_required
@require_POST
def calendar_reset(request):
    import uuid

    seller = seller_of(request.user)
    if seller:
        seller.calendar_token = uuid.uuid4()
        seller.save(update_fields=["calendar_token"])
        messages.success(request, "Nouveau lien d'agenda créé : l'ancien ne fonctionne plus. Réabonnez votre téléphone avec le nouveau.")
    return redirect("backoffice:planning")


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
            "blocks": vehicle.blocks.filter(period__endswith__gte=timezone.now()), "block_form": BlockForm(initial=_block_initial(request)),
        })
    return render(request, "backoffice/vehicle_form.html", ctx)


def _block_initial(request):
    """Clic sur un jour libre du planning : la période à bloquer est pré-remplie."""
    from datetime import date

    try:
        day = date.fromisoformat(request.GET.get("bloquer", ""))
    except ValueError:
        return {}
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    return {"start": start, "end": start + timedelta(days=1)}


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
