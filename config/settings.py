import os
import re
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _db_from_url(url):
    # Tolère une valeur collée avec espaces, guillemets ou la commande « psql '…' » copiée depuis Neon.
    match = re.search(r"postgres(?:ql)?://[^\s'\"]+", url)
    u = urlparse(match.group(0) if match else url.strip())
    options = {k: v[0] for k, v in parse_qs(u.query).items()}
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": u.path.lstrip("/"),
        "USER": unquote(u.username or ""),
        "PASSWORD": unquote(u.password or ""),
        "HOST": u.hostname,
        "PORT": u.port or 5432,
        "OPTIONS": options,
    }


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "rest_framework",
    "django_filters",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "axes",
    "accounts",
    "vehicles",
    "customers",
    "rentals",
    "payments",
    "backoffice",
    "pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Toujours en dernier : bloque les tentatives de connexion répétées.
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "backoffice.context_processors.roles",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Les prévisualisations Vercel ne doivent jamais toucher la base de production :
# elles utilisent PREVIEW_DATABASE_URL (branche Neon), sinon le démarrage automatique est désactivé.
VERCEL_ENV = os.environ.get("VERCEL_ENV", "")
_db_url = os.environ.get("DATABASE_URL")
if VERCEL_ENV == "preview" and os.environ.get("PREVIEW_DATABASE_URL"):
    _db_url = os.environ["PREVIEW_DATABASE_URL"]
PREVIEW_ON_PRODUCTION_DB = VERCEL_ENV == "preview" and not os.environ.get("PREVIEW_DATABASE_URL")

DATABASES = {
    "default": _db_from_url(_db_url) if _db_url else {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "autohub"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Libreville"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Pas de collectstatic en serverless : WhiteNoise sert depuis les apps installées.
WHITENOISE_USE_FINDERS = True
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Photos des véhicules : Vercel Blob si un magasin est relié au projet (BLOB_READ_WRITE_TOKEN),
# sinon dans la base PostgreSQL (aucune configuration ; le disque d'une fonction serverless n'est pas persistant).
BLOB_READ_WRITE_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
STORAGES = {
    "default": {"BACKEND": "vehicles.storage.VercelBlobStorage" if BLOB_READ_WRITE_TOKEN else "vehicles.storage.DatabaseStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MEDIA_UPLOADS_ENABLED = True
VEHICLE_MAX_PHOTOS = 20
PHOTO_MAX_BYTES = 4 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:home"
LOGOUT_REDIRECT_URL = "home"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min"},
}

# Marché : Gabon. Montants en francs CFA (XAF), sans centimes.
CURRENCY_CODE = "XAF"
CURRENCY_LABEL = "FCFA"

# Commission de la plateforme sur chaque location (montant de la location, hors caution).
PLATFORM_FEE_RATE = os.environ.get("PLATFORM_FEE_RATE", "0.02")
# Une demande de paiement Mobile Money non validée libère le véhicule après ce délai (minutes).
PENDING_PAYMENT_MINUTES = 15

# Paiement : "fake" (simulation) tant qu'un agrégateur Mobile Money n'est pas branché.
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "fake")
# Paiements en ligne : "demo" (simulés, bandeau visible), "off" (espèces à la remise des clés uniquement),
# "live" (agrégateur réel branché). Ne jamais lancer auprès du public en "demo".
# En production, le site est lancé pour de vrai : espèces uniquement tant qu'aucun agrégateur n'est branché.
ONLINE_PAYMENTS = os.environ.get("ONLINE_PAYMENTS", "off" if VERCEL_ENV == "production" else "demo")
# Le client peut annuler en ligne jusqu'à ce délai avant le départ (heures).
CUSTOMER_CANCEL_HOURS = 24

# Éditeur du site (mentions légales, contact). À renseigner dans les variables d'environnement.
SITE_NAME = "AutoHub"
SITE_URL = os.environ.get("SITE_URL", "https://autohub-five.vercel.app").rstrip("/")
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "monefan9")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "lomep610@gmail.com")
TERMS_VERSION = "2026-10"

# E-mails (mot de passe oublié, notifications). SMTP de n'importe quel fournisseur (Brevo, Resend, Gmail…) ;
# sans configuration, les e-mails sont écrits dans le journal.
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
    EMAIL_TIMEOUT = 10
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "AutoHub <no-reply@autohub.ga>")
# Annonces fictives chargées au démarrage si la base est vide (démonstration). 0 pour le lancement réel.
DEMO_DATA = os.environ.get("DEMO_DATA", "0" if VERCEL_ENV == "production" else "1") == "1"
# Tâches planifiées (rappels, expirations) déclenchées par Vercel Cron avec ce secret.
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# Règles métier location
RENTAL_MIN_DRIVER_AGE = 21
RENTAL_MIN_LICENSE_YEARS = 2

# Connexions : blocage 15 minutes après 5 échecs sur un même identifiant (quelle que soit l'IP)
# ou depuis une même IP (quel que soit l'identifiant). Un couple identifiant + IP se contournait en changeant d'IP.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "backoffice/lockout.html"
AXES_IPWARE_PROXY_COUNT = 1
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]

# Double authentification (TOTP) obligatoire pour l'admin.
OTP_TOTP_ISSUER = "AutoHub"

# Erreurs : journal sur la sortie standard (logs Vercel) et Sentry si SENTRY_DSN est défini.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
if os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=VERCEL_ENV or "local",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
