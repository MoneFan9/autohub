from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from customers.services import CustomerMismatch, get_or_create_customer
from payments.providers import PaymentDeclined
from rentals import pricing, services
from rentals.forms import BookingForm, PeriodForm, SearchForm, default_period
from rentals.models import Booking

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
        qs = Vehicle.objects.available_between(d["start"], d["end"]).select_related("agency")
        for field in ("agency", "category", "fuel", "transmission"):
            if d.get(field):
                qs = qs.filter(**{field: d[field]})
        if d.get("max_rate"):
            qs = qs.filter(daily_rate__lte=d["max_rate"])
        period = (d["start"], d["end"])
        vehicles = [(v, pricing.quote(v, *period)) for v in qs.order_by("daily_rate")]
    return render(request, "public/home.html", {"form": form, "results": vehicles, "period": period})


def vehicle_detail(request, pk):
    vehicle = get_object_or_404(Vehicle.objects.rentable().select_related("agency"), pk=pk)
    form = BookingForm(request.POST or None, initial=_period_initial(request))
    quote = None
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            customer = get_or_create_customer(form.customer_data())
            booking = services.create_booking(
                vehicle=vehicle, customer=customer, start=d["start"], end=d["end"],
                return_agency=d["return_agency"], extras=list(d["extras"]),
            )
        except (services.BookingError, CustomerMismatch) as exc:
            form.add_error(None, str(exc))
        else:
            try:
                services.pay_and_confirm(booking, form.payment_token())
            except PaymentDeclined as exc:
                services.cancel_booking(booking)
                field = "card_number" if form.cleaned_data["payment_method"] == "card" else "mobile_number"
                form.add_error(field, f"{exc} Vérifiez le numéro ou choisissez un autre moyen de paiement.")
            else:
                request.session[SESSION_BOOKINGS] = request.session.get(SESSION_BOOKINGS, []) + [booking.reference]
                messages.success(request, "Réservation confirmée.")
                return redirect("booking-confirmation", reference=booking.reference)
    period = PeriodForm(request.POST if request.method == "POST" else _period_initial(request))
    if period.is_valid():
        extras = form.cleaned_data.get("extras", []) if form.is_bound and hasattr(form, "cleaned_data") else []
        quote = pricing.quote(vehicle, period.cleaned_data["start"], period.cleaned_data["end"], list(extras))
    return render(request, "public/vehicle_detail.html", {"vehicle": vehicle, "form": form, "quote": quote})


def booking_confirmation(request, reference):
    # Visible uniquement par la session qui a réservé (pas d'énumération par référence).
    if reference not in request.session.get(SESSION_BOOKINGS, []):
        raise Http404
    booking = get_object_or_404(Booking.objects.select_related("vehicle", "customer", "pickup_agency", "return_agency"), reference=reference)
    return render(request, "public/confirmation.html", {"booking": booking})


def used_cars(request):
    qs = Vehicle.objects.for_sale().select_related("agency").order_by("sale_price")
    return render(request, "public/used_cars.html", {"vehicles": qs})
