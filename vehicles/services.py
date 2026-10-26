"""Photos et disponibilités des véhicules (utilisé par l'espace vendeur et l'admin)."""
import io
import uuid

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import Max
from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg.types.range import Range

from .models import VehicleBlock, VehiclePhoto

MAX_SIDE = 1600
QUALITY = 80


class VehicleError(Exception):
    pass


def _normalize(upload):
    """JPEG 1600 px max, orientation corrigée, métadonnées (dont position GPS) supprimées."""
    if upload.size > settings.PHOTO_MAX_BYTES * 3:
        raise VehicleError("Photo trop lourde (12 Mo maximum).")
    try:
        img = Image.open(upload)
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise VehicleError("Ce fichier n'est pas une photo lisible (JPEG, PNG ou WebP).") from exc
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return SimpleUploadedFile(f"{uuid.uuid4().hex[:12]}.jpg", out.getvalue(), content_type="image/jpeg")


def add_photo(vehicle, upload, kind=VehiclePhoto.Kind.OTHER):
    if not settings.MEDIA_UPLOADS_ENABLED:
        raise VehicleError("Le stockage des photos n'est pas encore activé sur le site.")
    if vehicle.photos.count() >= settings.VEHICLE_MAX_PHOTOS:
        raise VehicleError(f"{settings.VEHICLE_MAX_PHOTOS} photos maximum par véhicule.")
    image = _normalize(upload)
    position = (vehicle.photos.aggregate(m=Max("position"))["m"] or 0) + 1
    if kind not in VehiclePhoto.Kind.values:
        kind = VehiclePhoto.Kind.OTHER
    return VehiclePhoto.objects.create(vehicle=vehicle, image=image, kind=kind, position=position)


def delete_photo(photo):
    photo.image.delete(save=False)
    photo.delete()


@transaction.atomic
def move_photo(photo, direction):
    """direction : "up", "down" ou "cover" (en premier)."""
    photos = list(photo.vehicle.photos.select_for_update())
    i = photos.index(photo)
    if direction == "cover":
        photos.insert(0, photos.pop(i))
    elif direction == "up" and i > 0:
        photos[i - 1], photos[i] = photos[i], photos[i - 1]
    elif direction == "down" and i < len(photos) - 1:
        photos[i + 1], photos[i] = photos[i], photos[i + 1]
    for pos, p in enumerate(photos, start=1):
        if p.position != pos:
            VehiclePhoto.objects.filter(pk=p.pk).update(position=pos)


def missing_views(vehicle):
    """Vues conseillées pas encore photographiées."""
    done = set(vehicle.photos.values_list("kind", flat=True))
    return [VehiclePhoto.Kind(k).label for k in VehiclePhoto.RECOMMENDED if k not in done]


def block_period(vehicle, start, end, reason=""):
    from rentals.models import Booking

    if end <= start:
        raise VehicleError("La fin doit être après le début.")
    if Booking.objects.blocking().filter(vehicle=vehicle).overlapping(start, end).exists():
        raise VehicleError("Une réservation existe déjà sur cette période : annulez-la d'abord si besoin.")
    try:
        with transaction.atomic():
            return VehicleBlock.objects.create(vehicle=vehicle, period=Range(start, end, "[)"), reason=reason)
    except IntegrityError as exc:
        raise VehicleError("Cette période chevauche une indisponibilité déjà saisie.") from exc
