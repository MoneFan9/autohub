"""Stockage des photos sur Vercel Blob (API HTTP), sans dépendance supplémentaire.

Le nom enregistré en base est l'URL publique renvoyée par Vercel Blob.
"""
import json
import uuid
import urllib.request
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

API = "https://blob.vercel-storage.com"


@deconstructible
class VercelBlobStorage(Storage):
    def _request(self, method, url, data=None, headers=None):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "authorization": f"Bearer {settings.BLOB_READ_WRITE_TOKEN}",
            "x-api-version": "7",
            **(headers or {}),
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        return json.loads(body) if body else {}

    def _save(self, name, content):
        content.seek(0)
        result = self._request(
            "PUT", f"{API}/{quote(name)}", data=content.read(),
            headers={"x-content-type": getattr(content, "content_type", None) or "image/jpeg", "x-add-random-suffix": "1"},
        )
        return result["url"]

    def delete(self, name):
        if name.startswith("http"):
            self._request("POST", f"{API}/delete", data=json.dumps({"urls": [name]}).encode(),
                          headers={"content-type": "application/json"})

    def exists(self, name):
        return False

    def url(self, name):
        return name

    def get_available_name(self, name, max_length=None):
        return name


@deconstructible
class DatabaseStorage(Storage):
    """Photos en base PostgreSQL, servies par /fichiers/<nom> avec un long cache navigateur."""

    def _save(self, name, content):
        from .models import StoredFile

        content.seek(0)
        data = content.read()
        f = StoredFile.objects.create(name=name, content=data, size=len(data),
                                      content_type=getattr(content, "content_type", None) or "image/jpeg")
        return f.name

    def get_available_name(self, name, max_length=None):
        from .models import StoredFile

        base, dot, ext = name.rpartition(".")
        candidate = name
        while StoredFile.objects.filter(name=candidate).exists():
            candidate = f"{base}-{uuid.uuid4().hex[:6]}{dot}{ext}"
        return candidate

    def delete(self, name):
        from .models import StoredFile

        StoredFile.objects.filter(name=name).delete()

    def exists(self, name):
        from .models import StoredFile

        return StoredFile.objects.filter(name=name).exists()

    def open(self, name, mode="rb"):
        from django.core.files.base import ContentFile

        from .models import StoredFile

        return ContentFile(bytes(StoredFile.objects.get(name=name).content), name=name)

    def size(self, name):
        from .models import StoredFile

        return StoredFile.objects.get(name=name).size

    def url(self, name):
        from django.urls import reverse

        return reverse("stored-file", args=[name])
