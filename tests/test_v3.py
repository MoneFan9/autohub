"""V3 : photos, vidéo, indisponibilités, notifications, comptes, pages légales, partage."""
import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from accounts.models import TermsAcceptance
from rentals import services
from rentals.models import Booking
from vehicles.models import Report, Vehicle, VehicleBlock, VehiclePhoto

from .conftest import make_seller

D = timedelta(days=1)


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_UPLOADS_ENABLED = True
    settings.CONTACT_EMAIL = "patron@example.com"


def image_file(name="photo.png", size=(3000, 2000), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


def upload(client, vehicle, *files, kind="front", fetch=False):
    headers = {"HTTP_X_REQUESTED_WITH": "fetch"} if fetch else {}
    return client.post(f"/espace-vendeur/vehicules/{vehicle.pk}/photos/", {"images": list(files), "kind": kind}, **headers)


class TestPhotos:
    def test_upload_is_resized_and_shown_as_cover(self, client, agent, vehicle):
        client.force_login(agent)
        r = upload(client, vehicle, image_file())
        assert r.status_code == 302 and r["Location"].endswith("#photos")
        photo = VehiclePhoto.objects.get()
        img = Image.open(photo.image.open())
        assert img.format == "JPEG" and max(img.size) == 1600 and photo.kind == "front"
        html = client.get("/").content.decode()
        assert photo.image.url in html  # couverture dans les résultats

    def test_gps_metadata_is_removed(self, client, agent, vehicle):
        exif = Image.Exif()
        exif[0x8825] = {2: (4.0, 23.0, 0.0)}  # GPSInfo
        buf = io.BytesIO()
        Image.new("RGB", (800, 600)).save(buf, "JPEG", exif=exif)
        client.force_login(agent)
        upload(client, vehicle, SimpleUploadedFile("gps.jpg", buf.getvalue(), content_type="image/jpeg"))
        assert not Image.open(VehiclePhoto.objects.get().image.open()).getexif()

    def test_non_image_is_refused(self, client, agent, vehicle):
        client.force_login(agent)
        r = upload(client, vehicle, SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf"), fetch=True)
        assert r.status_code == 400 and "photo lisible" in r.json()["errors"][0]
        assert not VehiclePhoto.objects.exists()

    def test_other_seller_cannot_touch_photos(self, client, vehicle):
        client.force_login(make_seller("autre"))
        assert upload(client, vehicle, image_file()).status_code == 404

    def test_order_cover_kind_and_delete(self, client, agent, vehicle):
        client.force_login(agent)
        upload(client, vehicle, image_file("a.png"), image_file("b.png"), image_file("c.png"))
        a, b, c = vehicle.photos.all()
        url = f"/espace-vendeur/vehicules/{vehicle.pk}/photos/"
        client.post(f"{url}{c.pk}/", {"action": "cover"})
        assert list(vehicle.photos.all()) == [c, a, b]
        client.post(f"{url}{c.pk}/", {"action": "down"})
        assert list(vehicle.photos.all()) == [a, c, b]
        client.post(f"{url}{b.pk}/", {"action": "kind", "kind": "dashboard"})
        b.refresh_from_db()
        assert b.kind == "dashboard"
        client.post(f"{url}{a.pk}/", {"action": "delete"})
        assert list(vehicle.photos.all()) == [c, b]

    def test_photo_limit(self, client, agent, vehicle, settings):
        settings.VEHICLE_MAX_PHOTOS = 2
        client.force_login(agent)
        upload(client, vehicle, image_file(), image_file(), image_file())
        assert vehicle.photos.count() == 2

    def test_uploads_disabled_without_storage(self, client, agent, vehicle, settings):
        settings.MEDIA_UPLOADS_ENABLED = False
        client.force_login(agent)
        upload(client, vehicle, image_file())
        assert not VehiclePhoto.objects.exists()
        assert "pas encore activé" in client.get(f"/espace-vendeur/vehicules/{vehicle.pk}/modifier/").content.decode()

    def test_gallery_video_and_missing_views(self, client, agent, vehicle):
        vehicle.video_url = "https://youtu.be/dQw4w9WgXcQ"
        vehicle.save()
        client.force_login(agent)
        upload(client, vehicle, image_file(), kind="dashboard")
        edit = client.get(f"/espace-vendeur/vehicules/{vehicle.pk}/modifier/").content.decode()
        assert "Avant (3/4 avant)" in edit and "Vues conseillées manquantes" in edit
        page = client.get(f"/vehicules/{vehicle.pk}/").content.decode()
        assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in page and "Tableau de bord" in page
        assert 'property="og:image"' in page and '"@type": "Car"' in page


class TestAvailability:
    def test_block_hides_vehicle_and_refuses_booking(self, client, agent, vehicle, customer, t0):
        client.force_login(agent)
        fmt = "%Y-%m-%dT%H:%M"
        client.post(f"/espace-vendeur/vehicules/{vehicle.pk}/indisponibilites/",
                    {"start": t0.strftime(fmt), "end": (t0 + 3 * D).strftime(fmt), "reason": "Voyage"})
        assert VehicleBlock.objects.count() == 1
        assert not Vehicle.objects.available_between(t0 + D, t0 + 2 * D).exists()
        assert Vehicle.objects.available_between(t0 + 3 * D, t0 + 4 * D).exists()
        with pytest.raises(services.VehicleUnavailable, match="pas disponible"):
            services.create_booking(vehicle=vehicle, customer=customer, start=t0 + D, end=t0 + 2 * D)

    def test_block_over_existing_booking_refused(self, client, agent, vehicle, customer, t0):
        services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + D)
        client.force_login(agent)
        fmt = "%Y-%m-%dT%H:%M"
        client.post(f"/espace-vendeur/vehicules/{vehicle.pk}/indisponibilites/", {"start": t0.strftime(fmt), "end": (t0 + 2 * D).strftime(fmt)})
        assert not VehicleBlock.objects.exists()


class TestNotifications:
    def test_confirmation_emails_client_and_seller(self, vehicle, member, t0, django_capture_on_commit_callbacks):
        from customers.services import customer_for_user
        from datetime import date

        customer = customer_for_user(member, {"first_name": "Hugo", "last_name": "N", "phone": "077", "birth_date": date(1990, 1, 1),
                                              "license_number": "GA9", "license_issued_on": date(2010, 1, 1)})
        vehicle.agency.seller.user.email = "loueur@example.com"
        vehicle.agency.seller.user.save()
        with django_capture_on_commit_callbacks(execute=True):
            b = services.pay_and_confirm(services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + D), services.CASH_TOKEN)
        assert sorted(m.to[0] for m in mail.outbox) == ["hugo@example.com", "loueur@example.com"]
        assert any("GA9" in m.body for m in mail.outbox)  # le loueur reçoit le permis à vérifier
        mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            services.cancel_booking(b, by=vehicle.agency.seller.user)
        assert "annulée par le loueur" in mail.outbox[0].body

    def test_daily_task_requires_secret_and_sends_reminders(self, client, vehicle, customer, t0, settings):
        settings.CRON_SECRET = "s3cret"
        b = services.pay_and_confirm(services.create_booking(vehicle=vehicle, customer=customer, start=t0, end=t0 + D), services.CASH_TOKEN)
        assert client.get("/taches/quotidiennes/").status_code == 403
        r = client.get("/taches/quotidiennes/", HTTP_AUTHORIZATION="Bearer s3cret")
        assert r.json() == {"reminders": 1}
        b.refresh_from_db()
        assert b.reminder_sent_at and any("Votre départ approche" in m.subject for m in mail.outbox)
        assert client.get("/taches/quotidiennes/", HTTP_AUTHORIZATION="Bearer s3cret").json() == {"reminders": 0}


class TestAccounts:
    def test_signup_records_terms(self, client, db):
        client.post("/compte/inscription/", {"first_name": "A", "last_name": "B", "email": "a@example.com",
                                             "password1": "Un-mot-de-passe-1", "password2": "Un-mot-de-passe-1", "accept_terms": "on"})
        assert TermsAcceptance.objects.get().document == "terms"

    def test_signup_without_terms_is_refused(self, client, db):
        r = client.post("/compte/inscription/", {"first_name": "A", "last_name": "B", "email": "a@example.com",
                                                 "password1": "Un-mot-de-passe-1", "password2": "Un-mot-de-passe-1"})
        assert r.status_code == 200 and "Acceptez les conditions" in r.content.decode()

    def test_password_reset_by_email(self, client, member, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        assert 'href="/compte/mot-de-passe-oublie/"' in client.get("/compte/connexion/").content.decode()
        client.post("/compte/mot-de-passe-oublie/", {"email": "hugo@example.com"})
        link = next(line for line in mail.outbox[0].body.splitlines() if "/compte/reinitialiser/" in line)
        r = client.get(link.split("testserver")[1], follow=True)
        r = client.post(r.redirect_chain[-1][0], {"new_password1": "Tout-nouveau-9", "new_password2": "Tout-nouveau-9"})
        assert r.status_code == 302
        member.refresh_from_db()
        assert member.check_password("Tout-nouveau-9")

    def test_customer_cannot_cancel_within_24h(self, client, member, vehicle):
        from django.utils import timezone

        from .test_web import _web_booking

        client.force_login(member)
        _web_booking(client, vehicle, (timezone.now() + timedelta(hours=12)).replace(second=0, microsecond=0), payment_method="cash")
        b = Booking.objects.get()
        assert "contactez le loueur" in client.get("/compte/").content.decode()
        client.post(f"/compte/reservations/{b.reference}/annuler/")
        b.refresh_from_db()
        assert b.status == "confirmed"

    def test_delete_account_anonymizes(self, client, member, vehicle, t0):
        from .test_web import _web_booking

        client.force_login(member)
        _web_booking(client, vehicle, t0 + 3 * D, payment_method="cash")
        r = client.post("/compte/supprimer/", {"password": "Secret-789"})
        assert r.status_code == 200 and "réservations sont en cours ou à venir" in r.content.decode()
        b = Booking.objects.get()
        client.post(f"/compte/reservations/{b.reference}/annuler/")
        r = client.post("/compte/supprimer/", {"password": "Secret-789"})
        assert r.status_code == 302
        member.refresh_from_db()
        b.customer.refresh_from_db()
        assert not member.is_active and member.email == "" and b.customer.last_name == "supprimé" and b.customer.license_number == "—"

    def test_seller_deletion_withdraws_listings(self, client, agent, vehicle):
        client.force_login(agent)
        client.post("/compte/supprimer/", {"password": "Secret-123"})
        vehicle.refresh_from_db()
        assert vehicle.status == "sold" and not vehicle.is_rentable
        assert "Renault Clio" not in client.get("/").content.decode()


class TestPublic:
    def test_report_listing(self, client, vehicle):
        client.post(f"/occasions/{vehicle.pk}/signaler/", {"reason": "scam", "message": "Demande un acompte"})
        report = Report.objects.get()
        assert report.reason == "scam" and "Signalement" in mail.outbox[0].subject
        client.post(f"/occasions/{vehicle.pk}/signaler/", {"reason": "scam", "website": "spam"})
        assert Report.objects.count() == 1

    def test_legal_pages_sitemap_robots(self, client, vehicle):
        for slug in ("cgu", "confidentialite", "mentions-legales", "annulation"):
            assert client.get(f"/infos/{slug}/").status_code == 200
        assert "001/2011" in client.get("/infos/confidentialite/").content.decode()
        assert f"/vehicules/{vehicle.pk}/" in client.get("/sitemap.xml").content.decode()
        assert "Sitemap:" in client.get("/robots.txt").content.decode()
        assert 'href="/infos/cgu/"' in client.get("/").content.decode()

    @override_settings(ONLINE_PAYMENTS="off")
    def test_payments_off_offers_cash_only(self, client, vehicle):
        html = client.get(f"/vehicules/{vehicle.pk}/").content.decode()
        assert 'value="cash"' in html and 'value="airtel"' not in html and "Site en démonstration" not in html

    def test_demo_banner(self, client, db):
        assert "Site en démonstration" in client.get("/").content.decode()



class TestDatabaseStorage:
    def test_photo_is_stored_in_database_and_served_with_cache(self, client, agent, vehicle):
        from vehicles.models import StoredFile

        client.force_login(agent)
        upload(client, vehicle, image_file())
        photo = VehiclePhoto.objects.get()
        assert photo.image.url.startswith("/fichiers/vehicules/") and StoredFile.objects.count() == 1
        r = client.get(photo.image.url)
        assert r.status_code == 200 and r["Content-Type"] == "image/jpeg" and "immutable" in r["Cache-Control"]
        assert Image.open(io.BytesIO(r.content)).size[0] == 1600
        client.post(f"/espace-vendeur/vehicules/{vehicle.pk}/photos/{photo.pk}/", {"action": "delete"})
        assert not StoredFile.objects.exists()

    def test_production_defaults_are_launch_settings(self, monkeypatch):
        import importlib

        import config.settings as conf

        monkeypatch.setenv("VERCEL_ENV", "production")
        monkeypatch.delenv("ONLINE_PAYMENTS", raising=False)
        monkeypatch.delenv("DEMO_DATA", raising=False)
        try:
            importlib.reload(conf)
            assert conf.ONLINE_PAYMENTS == "off" and conf.DEMO_DATA is False
        finally:
            monkeypatch.delenv("VERCEL_ENV")
            importlib.reload(conf)
