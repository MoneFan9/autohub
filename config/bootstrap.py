"""Démarrage serverless : migre et charge la démo une seule fois (verrou consultatif Postgres)."""
import os

from django.core.management import call_command
from django.db import connection

LOCK_ID = 7_340_001


def run():
    if os.environ.get("AUTO_BOOTSTRAP") != "1":
        return
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", [LOCK_ID])
        try:
            call_command("migrate", interactive=False, verbosity=0)
            from vehicles.models import Vehicle

            if not Vehicle.objects.exists():
                call_command("seed_demo", verbosity=0)
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])
