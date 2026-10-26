"""Frise de planning (une ligne par véhicule, une colonne par jour) et flux d'agenda iCalendar."""
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone
from psycopg.types.range import Range

from rentals.models import Booking
from vehicles.models import VehicleBlock

SPANS = (7, 14, 30)


def parse_window(params):
    """?debut=AAAA-MM-JJ&jours=7|14|30 ; par défaut aujourd'hui sur 14 jours."""
    try:
        first = date.fromisoformat(params.get("debut", ""))
    except ValueError:
        first = timezone.localdate()
    try:
        span = int(params.get("jours", 14))
    except ValueError:
        span = 14
    return first, span if span in SPANS else 14


def _midnight(d):
    return timezone.make_aware(datetime.combine(d, datetime.min.time()))


def build_rows(vehicles, bookings, blocks, first, span):
    """Pour chaque véhicule, une suite de segments {kind, span, obj, day} couvrant la fenêtre.

    Un séjour sur plusieurs jours devient un seul segment (colspan) ; les jours libres restent cliquables.
    """
    start, end = _midnight(first), _midnight(first + timedelta(days=span))
    events = {}
    for b in bookings:
        events.setdefault(b.vehicle_id, []).append(("booking", b, b.start, b.end))
    for k in blocks:
        events.setdefault(k.vehicle_id, []).append(("block", k, k.start, k.end))

    def day_index(moment, upper=False):
        local = timezone.localtime(max(start, min(moment, end)))
        i = (local.date() - first).days
        if upper and (local.time() != datetime.min.time() or local.date() == first):
            i += 1  # un retour à 10 h occupe encore la journée
        return max(0, min(span, i))

    rows = []
    for v in vehicles:
        taken = [None] * span
        for kind, obj, s, e in sorted(events.get(v.id, []), key=lambda x: x[2]):
            a, z = day_index(s), day_index(e, upper=True)
            for i in range(a, max(a + 1, z)):
                if i < span and taken[i] is None:
                    taken[i] = (kind, obj)
        segments, i = [], 0
        while i < span:
            cur = taken[i]
            j = i + 1
            while cur and j < span and taken[j] is not None and taken[j][1] is cur[1]:
                j += 1
            day = first + timedelta(days=i)
            segments.append({"kind": cur[0] if cur else "free", "obj": cur[1] if cur else None, "span": j - i, "day": day})
            i = j
        busy = sum(1 for t in taken if t and t[0] == "booking")
        rows.append({"vehicle": v, "segments": segments, "occupancy": round(100 * busy / span)})
    return rows


def window_queries(bookings_qs, vehicles, first, span):
    start, end = _midnight(first), _midnight(first + timedelta(days=span))
    window = Range(start, end, "[)")
    bookings = bookings_qs.blocking().filter(period__overlap=window).select_related("customer")
    blocks = VehicleBlock.objects.filter(vehicle__in=vehicles, period__overlap=window)
    return bookings, blocks


# --- iCalendar (RFC 5545) -------------------------------------------------------------------------

def _esc(text):
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _dt(moment):
    return moment.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold(line):
    out, raw = [], line.encode()
    while len(raw) > 75:
        cut = 75
        while (raw[cut] & 0xC0) == 0x80:  # ne pas couper un caractère UTF-8
            cut -= 1
        out.append(raw[:cut].decode())
        raw = b" " + raw[cut:]
    out.append(raw.decode())
    return "\r\n".join(out)


def ical(seller, site_url):
    now = timezone.now()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AutoHub//Planning//FR", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_esc('AutoHub · ' + seller.display_name)}", "X-WR-TIMEZONE:Africa/Libreville"]
    bookings = (Booking.objects.blocking().filter(vehicle__agency__seller=seller, period__endswith__gte=now - timedelta(days=30))
                .select_related("vehicle", "customer", "pickup_agency"))
    for b in bookings:
        due = b.balance_due
        desc = (f"Réservation {b.reference} ({b.get_status_display().lower()})\nClient : {b.customer} · {b.customer.phone}\n"
                f"Total : {b.total_amount:.0f} FCFA ({b.payment_label})" + (f", {due:.0f} FCFA à encaisser" if due else "")
                + f"\nCaution : {b.deposit_amount:.0f} FCFA\n{site_url}/espace-vendeur/reservations/{b.reference}/")
        lines += ["BEGIN:VEVENT", f"UID:{b.reference}@autohub", f"DTSTAMP:{_dt(now)}", f"DTSTART:{_dt(b.start)}", f"DTEND:{_dt(b.end)}",
                  f"SUMMARY:{_esc(b.vehicle.title + ' · ' + b.customer.last_name)}",
                  f"LOCATION:{_esc(b.pickup_agency.name + ', ' + b.pickup_agency.city)}", f"DESCRIPTION:{_esc(desc)}",
                  "STATUS:" + ("TENTATIVE" if b.status == Booking.Status.PENDING else "CONFIRMED"), "END:VEVENT"]
    for k in VehicleBlock.objects.filter(vehicle__agency__seller=seller, period__endswith__gte=now).select_related("vehicle"):
        lines += ["BEGIN:VEVENT", f"UID:block-{k.pk}@autohub", f"DTSTAMP:{_dt(now)}", f"DTSTART:{_dt(k.start)}", f"DTEND:{_dt(k.end)}",
                  f"SUMMARY:{_esc(k.vehicle.title + ' · indisponible')}", f"DESCRIPTION:{_esc(k.reason)}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
