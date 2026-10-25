from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from vehicles.models import Vehicle

from .views import LEGAL_PAGES


class StaticSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return ["home", "used-cars"] + [f"legal:{slug}" for slug in LEGAL_PAGES]

    def location(self, item):
        if item.startswith("legal:"):
            return reverse("legal", args=[item.split(":", 1)[1]])
        return reverse(item)


class RentalSitemap(Sitemap):
    changefreq = "daily"

    def items(self):
        return Vehicle.objects.rentable()

    def location(self, v):
        return reverse("vehicle-detail", args=[v.pk])

    def lastmod(self, v):
        return v.updated_at


class SaleSitemap(RentalSitemap):
    def items(self):
        return Vehicle.objects.for_sale()

    def location(self, v):
        return reverse("used-car-detail", args=[v.pk])


SITEMAPS = {"pages": StaticSitemap, "location": RentalSitemap, "occasions": SaleSitemap}
