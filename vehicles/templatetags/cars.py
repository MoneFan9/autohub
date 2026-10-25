from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.conf import settings

register = template.Library()

# Teinte de carrosserie de l'illustration, à partir de la couleur saisie en texte libre.
PAINTS = {
    "noir": "#23272e",
    "gris": "#8a939e",
    "blanc": "#eef1f4",
    "bleu": "#2f5fb3",
    "rouge": "#c0392b",
    "vert": "#2e7d5b",
}
DEFAULT_PAINT = "#5b6573"


@register.filter
def fcfa(amount):
    """25000 -> « 25 000 FCFA » (espace fine insécable, sans centimes)."""
    if amount in (None, ""):
        return ""
    n = int(Decimal(str(amount)).quantize(Decimal("1"), ROUND_HALF_UP))
    return f"{n:,}".replace(",", "\u202f") + "\u00a0" + settings.CURRENCY_LABEL


@register.filter
def paint(color):
    return PAINTS.get((color or "").strip().lower(), DEFAULT_PAINT)


@register.filter
def silhouette(category):
    return {"premium": "sedan"}.get(category, category)
