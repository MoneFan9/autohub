from django import template

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
def paint(color):
    return PAINTS.get((color or "").strip().lower(), DEFAULT_PAINT)


@register.filter
def silhouette(category):
    return {"premium": "sedan"}.get(category, category)
