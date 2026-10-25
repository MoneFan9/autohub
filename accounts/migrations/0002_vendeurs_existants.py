from django.db import migrations


def forwards(apps, schema_editor):
    """V1 -> V2 : les membres du groupe « Agence » deviennent vendeurs ; les lieux sans vendeur leur reviennent."""
    User = apps.get_model("auth", "User")
    Seller = apps.get_model("accounts", "Seller")
    Agency = apps.get_model("vehicles", "Agency")
    first = None
    for user in User.objects.filter(groups__name="Agence").order_by("pk"):
        seller, _ = Seller.objects.get_or_create(user=user, defaults={
            "display_name": "Loc'Auto Libreville", "kind": "pro", "city": "Libreville", "phone": "+241 01 00 00 01",
            "accepts_airtel": True, "accepts_moov": True, "accepts_card": True, "accepts_cash": True,
            "payout_number": "+241 01 00 00 01",
        })
        first = first or seller
    if first:
        Agency.objects.filter(seller__isnull=True).update(seller=first)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_place_de_marche"),
        ("vehicles", "0003_place_de_marche"),
        ("backoffice", "0001_agency_group"),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
