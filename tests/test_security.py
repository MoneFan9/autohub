from django.test import override_settings
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice


def code(device):
    return f"{totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits):06d}"


def test_owner_enrolls_totp_and_reaches_admin(client, owner):
    client.post("/compte/connexion/", {"username": "patron", "password": "Secret-456"})
    page = client.get("/compte/securite/")
    assert page.status_code == 200 and "<svg" in page.content.decode()
    device = TOTPDevice.objects.get(user=owner, confirmed=False)
    assert client.post("/compte/securite/", {"token": "000000"}).status_code == 200  # mauvais code
    # Après un échec, django-otp impose un court délai : on le lève pour le test.
    TOTPDevice.objects.filter(pk=device.pk).update(throttling_failure_count=0, throttling_failure_timestamp=None)
    r = client.post("/compte/securite/", {"token": code(device)})
    assert r.status_code == 302 and r["Location"] == "/admin/"
    assert client.get("/admin/").status_code == 200


def test_admin_login_requires_password_and_code(client, owner):
    device = TOTPDevice.objects.create(user=owner, name="tel", confirmed=True)
    r = client.post("/admin/login/?next=/admin/", {"username": "patron", "password": "Secret-456", "otp_token": ""})
    assert r.status_code == 200 and client.get("/admin/").status_code == 302
    r = client.post("/admin/login/?next=/admin/", {"username": "patron", "password": "Secret-456", "otp_token": code(device)})
    assert r.status_code == 302 and client.get("/admin/").status_code == 200


def test_enrollment_page_cannot_add_second_device(client, owner):
    TOTPDevice.objects.create(user=owner, name="tel", confirmed=True)
    client.force_login(owner)
    html = client.get("/compte/securite/").content.decode()
    assert "Activée sur votre compte" in html and "<svg" not in html.split("Activée")[1]
    assert TOTPDevice.objects.filter(user=owner).count() == 1


def test_seller_cannot_open_security_page(client, agent):
    client.force_login(agent)
    assert client.get("/compte/securite/").status_code == 302


def test_login_locked_after_five_failures(client, agent):
    for _ in range(5):
        client.post("/compte/connexion/", {"username": "agent", "password": "faux"}, REMOTE_ADDR="10.0.0.1")
    r = client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123"}, REMOTE_ADDR="10.0.0.1")
    assert r.status_code == 429 and "temporairement bloquée" in r.content.decode()
    assert "_auth_user_id" not in client.session
    # Changer d'adresse IP ne contourne pas le blocage.
    r = client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123"}, REMOTE_ADDR="10.0.0.2")
    assert r.status_code == 429


def test_failures_spread_over_ips_still_lock(client, agent):
    for i in range(5):
        client.post("/compte/connexion/", {"username": "agent", "password": "faux"}, REMOTE_ADDR=f"10.0.1.{i}")
    r = client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123"}, REMOTE_ADDR="10.0.1.99")
    assert r.status_code == 429


def test_member_changes_password(client, agent):
    client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123"})
    r = client.post("/compte/mot-de-passe/", {"old_password": "Secret-123", "new_password1": "Nouveau-mdp-2026", "new_password2": "Nouveau-mdp-2026"})
    assert r.status_code == 302
    agent.refresh_from_db()
    assert agent.check_password("Nouveau-mdp-2026")


@override_settings(PREVIEW_ON_PRODUCTION_DB=True)
def test_preview_on_production_db_never_bootstraps(monkeypatch):
    from config import bootstrap

    calls = []
    monkeypatch.setenv("AUTO_BOOTSTRAP", "1")
    monkeypatch.setattr(bootstrap, "call_command", lambda *a, **k: calls.append(a))
    bootstrap.run()
    assert calls == []


def test_many_usernames_from_one_ip_lock_the_ip(client, agent):
    for i in range(5):
        client.post("/compte/connexion/", {"username": f"inconnu{i}", "password": "faux"}, REMOTE_ADDR="10.0.2.1")
    r = client.post("/compte/connexion/", {"username": "agent", "password": "Secret-123"}, REMOTE_ADDR="10.0.2.1")
    assert r.status_code == 429


def test_database_url_tolerates_pasted_command():
    from config.settings import _db_from_url

    for raw in [" postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require\n",
                "psql 'postgresql://u:p@ep-x.neon.tech/neondb?sslmode=require'"]:
        db = _db_from_url(raw)
        assert (db["HOST"], db["NAME"], db["OPTIONS"]) == ("ep-x.neon.tech", "neondb", {"sslmode": "require"})
