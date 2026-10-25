from django.db import migrations


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("auth", "User")
    group, _ = Group.objects.get_or_create(name="Agence")
    # Le compte de démo « agent » était superutilisateur : il devient un simple membre d'agence.
    for user in User.objects.filter(username="agent"):
        user.is_superuser = False
        user.is_staff = False
        user.save(update_fields=["is_superuser", "is_staff"])
        user.groups.add(group)


class Migration(migrations.Migration):
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
