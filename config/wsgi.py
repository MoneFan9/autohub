import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

from config import bootstrap  # noqa: E402

bootstrap.run()

app = application  # point d'entrée Vercel
