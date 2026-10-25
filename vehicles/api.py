import django_filters
from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError

from .models import Agency, Vehicle


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = ["id", "name", "city", "address", "phone"]


class VehicleSerializer(serializers.ModelSerializer):
    agency = AgencySerializer(read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id", "brand", "model", "year", "mileage", "fuel", "transmission", "category",
            "seats", "color", "description", "photo", "agency", "status",
            "is_rentable", "is_for_sale", "daily_rate", "sale_price",
        ]


class VehicleFilter(django_filters.FilterSet):
    max_daily_rate = django_filters.NumberFilter(field_name="daily_rate", lookup_expr="lte")
    max_sale_price = django_filters.NumberFilter(field_name="sale_price", lookup_expr="lte")
    max_mileage = django_filters.NumberFilter(field_name="mileage", lookup_expr="lte")
    min_year = django_filters.NumberFilter(field_name="year", lookup_expr="gte")
    brand = django_filters.CharFilter(lookup_expr="iexact")

    class Meta:
        model = Vehicle
        fields = ["brand", "fuel", "transmission", "category", "agency", "is_rentable", "is_for_sale"]


class AgencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Agency.objects.all()
    serializer_class = AgencySerializer


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    """Catalogue public. `?start=&end=` (ISO 8601) ne garde que les véhicules libres sur la période."""

    serializer_class = VehicleSerializer
    filterset_class = VehicleFilter

    def get_queryset(self):
        qs = Vehicle.objects.exclude(status=Vehicle.Status.SOLD).select_related("agency")
        start, end = self.request.query_params.get("start"), self.request.query_params.get("end")
        if start and end:
            f = serializers.DateTimeField()
            try:
                start, end = f.to_internal_value(start), f.to_internal_value(end)
            except serializers.ValidationError:
                raise ValidationError({"start": "Dates ISO 8601 attendues."})
            if end <= start:
                raise ValidationError({"end": "La fin doit être après le début."})
            qs = qs.available_between(start, end)
        return qs
