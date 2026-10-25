from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from customers.services import customer_for_user
from payments.providers import PaymentDeclined
from payments.services import MOBILE_MONEY
from rentals import notifications, pricing, services
from rentals.forms import BookingForm, PeriodForm, SearchForm, default_period
from rentals.models import Booking

from .forms import ReportForm
from .models import Vehicle

SESSION_BOOKINGS = "my_bookings"


def _period_initial(request):
    start, end = default_period()
    return {"start": request.GET.get("start") or start.strftime("%Y-%m-%dT%H:%M"),
            "end": request.GET.get("end") or end.strftime("%Y-%m-%dT%H:%M")}


def home(request):
    params = request.GET.copy()
    for k, v in _period_initial(request).items():
        params.setdefault(k, v)
    form = SearchForm(params)
    vehicles, period = [], None
    if form.is_valid():
        d = form.cleaned_data
        services.expire_stale_pending(None)
        qs = Vehicle.objects.available_between(d["start"], d["end"]).select_related("agency__seller").prefetch_related("photos")
        if d.get("city"):
            qs = qs.filter(agency__city=d["city"])
        for field in ("category", "fuel", "transmission"):
            if d.get(field):
                qs = qs.filter(**{field: d[field]})
        if d.get("max_rate"):
            qs = qs.filter(daily_rate__lte=d["max_rate"])
        period = (d["start"], d["end"])
        vehicles = [(v, pricing.quote(v, *period)) for v in qs.order_by("daily_rate")]
    return render(request, "public/home.html", {"form": form, "results": vehicles, "period": period})


def _remember(request, booking):
    request.session[SESSION_BOOKINGS] = request.session.get(SESSION_BOOKINGS, []) + [booking.reference]


def _driver_initial(user):
    if not user.is_authenticated:
        return {}
    c = getattr(user, "customer", None)
    base = {"first_name": user.first_name, "last_name": user.last_name}
    if c:
        base.update({f: getattr(c, f) for f in BookingForm.CUSTOMER_FIELDS})
    return base


def vehicle_detail(request, pk):
    services.expire_stale_pending(None)
    vehicle = get_object_or_404(Vehicle.objects.rentable().select_related("agency__seller").prefetch_related("photos"), pk=pk)
    seller = vehicle.agency.seller
    methods = seller.payment_methods if seller else None
    form = BookingForm(request.POST or None, initial={**_period_initial(request), **_driver_initial(request.user)}, methods=methods, seller=seller)
    quote = None
    if request.method == "POST" and not request.user.is_authenticated:
        return redirect(f"{reverse('accounts:login')}?next={request.path}")
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            customer = customer_for_user(request.user, form.customer_data())
            booking = services.create_booking(
                vehicle=vehicle, customer=customer, start=d["start"], end=d["end"],
                return_agency=d["return_agency"], extras=list(d["extras"]),
            )
        except services.BookingError as exc:
            form.add_error(None, str(exc))
        else:
            method = d["payment_method"]
            _remember(request, booking)
            if method in MOBILE_MONEY:
                services.start_mobile_payment(booking, method, d["mobile_number"])
                return redirect("booking-payment", reference=booking.reference)
            try:
                services.pay_and_confirm(booking, form.payment_token())
            except PaymentDeclined as exc:
                services.cancel_booking(booking)
                form.add_error("card_number", f"{exc} Vérifiez le numéro ou choisissez un autre moyen de paiement.")
            else:
                messages.success(request, "Réservation confirmée.")
                return redirect("booking-confirmation", reference=booking.reference)
    period = PeriodForm(request.POST if request.method == "POST" else _period_initial(request))
    if period.is_valid():
        extras = form.cleaned_data.get("extras", []) if form.is_bound and hasattr(form, "cleaned_data") else []
        quote = pricing.quote(vehicle, period.cleaned_data["start"], period.cleaned_data["end"], list(extras))
    return render(request, "public/vehicle_detail.html", {"vehicle": vehicle, "seller": seller, "form": form, "quote": quote, "report_form": ReportForm()})


def _visible_booking(request, reference):
    booking = get_object_or_404(Booking.objects.select_related("vehicle__agency__seller", "customer", "pickup_agency", "return_agency"), reference=reference)
    mine = request.user.is_authenticated and booking.customer.user_id == request.user.id
    # Visible uniquement par son client (pas d'énumération par référence).
    if not mine and reference not in request.session.get(SESSION_BOOKINGS, []):
        raise Http404
    return booking


def booking_payment(request, reference):
    """Mobile Money : le client valide la demande de paiement sur son téléphone."""
    booking = _visible_booking(request, reference)
    if booking.status == Booking.Status.CONFIRMED:
        return redirect("booking-confirmation", reference=reference)
    if request.method == "POST" and booking.status == Booking.Status.PENDING:
        status = services.finalize_mobile_payment(booking)
        if status == "succeeded":
            messages.success(request, "Paiement reçu, réservation confirmée.")
            return redirect("booking-confirmation", reference=reference)
        if status == "pending":
            messages.info(request, "Paiement pas encore validé. Validez la demande sur votre téléphone puis réessayez.")
        booking.refresh_from_db()
    payment = booking.payments.filter(kind="charge").order_by("-created_at").first()
    return render(request, "public/booking_payment.html",
                  {"booking": booking, "payment": payment, "hold_minutes": settings.PENDING_PAYMENT_MINUTES})


def booking_confirmation(request, reference):
    booking = _visible_booking(request, reference)
    if booking.status == Booking.Status.PENDING:
        return redirect("booking-payment", reference=reference)
    return render(request, "public/confirmation.html", {"booking": booking})


def used_cars(request):
    qs = Vehicle.objects.for_sale().select_related("agency__seller").prefetch_related("photos").order_by("sale_price")
    return render(request, "public/used_cars.html", {"vehicles": qs})


def used_car_detail(request, pk):
    vehicle = get_object_or_404(Vehicle.objects.for_sale().select_related("agency__seller").prefetch_related("photos"), pk=pk)
    return render(request, "public/used_car_detail.html", {"vehicle": vehicle, "seller": vehicle.agency.seller, "report_form": ReportForm()})


@require_POST
def report_vehicle(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    back = reverse("used-car-detail" if vehicle.is_for_sale else "vehicle-detail", args=[pk])
    form = ReportForm(request.POST)
    if request.POST.get("website"):  # piège à robots
        return redirect(back)
    if form.is_valid():
        report = form.save(commit=False)
        report.vehicle = vehicle
        report.reporter = request.user if request.user.is_authenticated else None
        report.save()
        notifications.vehicle_reported(report)
        messages.success(request, "Merci, le signalement a été transmis. Il sera examiné rapidement.")
    else:
        messages.error(request, "Choisissez un motif pour signaler l'annonce.")
    return redirect(back)
