from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from backoffice.roles import IsAgencyMember
from customers.models import Customer
from customers.services import CustomerMismatch, get_or_create_customer
from payments.providers import PaymentDeclined
from vehicles.models import Agency, Vehicle

from . import pricing, services
from .models import Booking, Extra


class ExtraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Extra
        fields = ["code", "label", "price_per_day", "max_price"]


class PeriodMixin(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    extras = serializers.SlugRelatedField(slug_field="code", queryset=Extra.objects.all(), many=True, required=False)

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "La fin doit être après le début."})
        return attrs


class QuoteRequestSerializer(PeriodMixin):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.rentable())


class QuoteSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    base_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    extras_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    deposit_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["first_name", "last_name", "email", "phone", "birth_date", "license_number", "license_issued_on"]
        extra_kwargs = {"email": {"validators": []}}


class BookingCreateSerializer(PeriodMixin):
    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    customer = CustomerSerializer()
    return_agency = serializers.PrimaryKeyRelatedField(queryset=Agency.objects.all(), required=False)
    payment_token = serializers.CharField(write_only=True)


class BookingSerializer(serializers.ModelSerializer):
    vehicle = serializers.StringRelatedField()
    customer = serializers.StringRelatedField()
    start = serializers.DateTimeField(read_only=True)
    end = serializers.DateTimeField(read_only=True)
    extras = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)

    class Meta:
        model = Booking
        fields = [
            "reference", "status", "vehicle", "customer", "start", "end", "pickup_agency", "return_agency",
            "extras", "days", "base_amount", "extras_amount", "discount_amount", "total_amount", "deposit_amount",
        ]


class InspectionSerializer(serializers.Serializer):
    mileage = serializers.IntegerField(min_value=0)
    fuel_level = serializers.IntegerField(min_value=0, max_value=100)
    damages = serializers.CharField(required=False, allow_blank=True, default="")
    cash_received = serializers.BooleanField(required=False, default=False)


class ExtraViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Extra.objects.all()
    serializer_class = ExtraSerializer
    lookup_field = "code"


class BookingViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Création publique (paiement inclus). Lecture et actions réservées aux membres d'agence."""

    queryset = Booking.objects.select_related("vehicle", "customer").prefetch_related("extras")
    serializer_class = BookingSerializer
    lookup_field = "reference"
    filterset_fields = ["status", "vehicle", "pickup_agency"]

    def get_permissions(self):
        if self.action in ("create", "quote"):
            return [permissions.AllowAny()]
        return [IsAgencyMember()]

    @action(detail=False, methods=["post"])
    def quote(self, request):
        s = QuoteRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        q = pricing.quote(d["vehicle"], d["start"], d["end"], d.get("extras", []))
        return Response(QuoteSerializer(q).data)

    def create(self, request, *args, **kwargs):
        s = BookingCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            customer = get_or_create_customer(d["customer"])
        except CustomerMismatch as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        try:
            booking = services.create_booking(
                vehicle=d["vehicle"], customer=customer, start=d["start"], end=d["end"],
                return_agency=d.get("return_agency"), extras=d.get("extras", []),
            )
        except services.BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        try:
            services.pay_and_confirm(booking, d["payment_token"])
        except PaymentDeclined as exc:
            services.cancel_booking(booking)
            return Response({"detail": str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    def _transition(self, request, fn, with_inspection=True, drop=()):
        booking = self.get_object()
        kwargs = {}
        if with_inspection:
            s = InspectionSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            kwargs = {k: v for k, v in s.validated_data.items() if k not in drop}
            kwargs["user"] = request.user
        try:
            fn(booking, **kwargs)
        except services.BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        booking.refresh_from_db()
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=["post"])
    def start(self, request, reference=None):
        return self._transition(request, services.start_rental)

    @action(detail=True, methods=["post"])
    def complete(self, request, reference=None):
        return self._transition(request, services.complete_rental, drop=("cash_received",))

    @action(detail=True, methods=["post"])
    def cancel(self, request, reference=None):
        return self._transition(request, services.cancel_booking, with_inspection=False)
