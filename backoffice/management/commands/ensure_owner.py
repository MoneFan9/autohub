import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Crée le compte propriétaire (superutilisateur) depuis OWNER_USERNAME / OWNER_PASSWORD s'il n'existe pas."

    def handle(self, *args, **opts):
        username, password = os.environ.get("OWNER_USERNAME"), os.environ.get("OWNER_PASSWORD")
        if not username or not password:
            return
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            return
        User.objects.create_superuser(username, "", password)
        self.stdout.write(self.style.SUCCESS(f"Compte propriétaire « {username} » créé."))
