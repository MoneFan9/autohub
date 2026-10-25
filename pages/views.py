import hmac

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from rentals import services

LEGAL_PAGES = {
    "cgu": "Conditions générales d'utilisation",
    "confidentialite": "Politique de confidentialité",
    "mentions-legales": "Mentions légales",
    "annulation": "Annulation, caution et litiges",
}


def legal(request, slug):
    if slug not in LEGAL_PAGES:
        raise Http404
    return render(request, f"legal/{slug}.html", {"title": LEGAL_PAGES[slug], "pages": LEGAL_PAGES, "slug": slug,
                                                 "cancel_hours": settings.CUSTOMER_CANCEL_HOURS})


@require_GET
def robots(request):
    lines = ["User-agent: *", "Disallow: /compte/", "Disallow: /espace-vendeur/", "Disallow: /admin/",
             "Disallow: /reservation/", "Disallow: /api/", f"Sitemap: {settings.SITE_URL}{reverse('sitemap')}"]
    if settings.VERCEL_ENV == "preview":
        lines = ["User-agent: *", "Disallow: /"]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def daily_tasks(request):
    """Appelée chaque jour par Vercel Cron (en-tête Authorization: Bearer CRON_SECRET)."""
    expected = f"Bearer {settings.CRON_SECRET}"
    if not settings.CRON_SECRET or not hmac.compare_digest(request.headers.get("Authorization", ""), expected):
        return HttpResponseForbidden()
    services.expire_stale_pending(None)
    return JsonResponse({"reminders": services.send_departure_reminders()})
