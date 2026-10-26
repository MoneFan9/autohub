import uuid

from django.db import migrations, models


def fill_tokens(apps, schema_editor):
    Seller = apps.get_model("accounts", "Seller")
    for seller in Seller.objects.all():
        seller.calendar_token = uuid.uuid4()
        seller.save(update_fields=["calendar_token"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_v3_lancement")]

    operations = [
        migrations.AddField(model_name="seller", name="calendar_token", field=models.UUIDField(null=True, editable=False)),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(model_name="seller", name="calendar_token",
                              field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
    ]
