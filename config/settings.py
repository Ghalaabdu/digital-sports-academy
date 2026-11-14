"""
إعدادات خادم «أكاديمية الرياضة الرقمية».
كل القيم الحساسة تُقرأ من ملف .env (انظري .env.example).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Python المثبّت من python.org على الماك لا يحمل شهادات SSL — نستخدم حزمة certifi
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass


def env(key, default=""):
    return os.getenv(key, default)


def env_bool(key, default=False):
    return env(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(key):
    return [x.strip() for x in env(key).split(",") if x.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS") or ["127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------- قاعدة البيانات ----------
if env("DB_ENGINE", "postgres").lower() == "sqlite":
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "sports_academy"),
            "USER": env("DB_USER", "postgres"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "127.0.0.1"),
            "PORT": env("DB_PORT", "5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "core.validators.UppercaseValidator"},
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------- الجلسات والأمان ----------
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # أسبوعان
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # الواجهة تقرأ رمز CSRF وترسله في الترويسة
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------- البريد ----------
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@localhost")
EMAIL_TIMEOUT = 20
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD
    else "django.core.mail.backends.console.EmailBackend"
)

# ---------- رموز التحقق ----------
CODE_TTL_MINUTES = 15
CODE_RESEND_SECONDS = 60
CODE_MAX_ATTEMPTS = 5

# ---------- Gemini ----------
GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.5-flash")
# بدائل تُجرَّب تلقائياً إذا كان النموذج الأساسي مضغوطاً أو غير متاح
GEMINI_FALLBACK_MODELS = env_list("GEMINI_FALLBACK_MODELS") or ["gemini-3.8-flash", "gemini-3.7-flash"]
GEMINI_TIMEOUT_MS = int(env("GEMINI_TIMEOUT_MS", "20000"))

# ---------- الخطوات ----------
STEPS_REQUIRE_PROOF = env_bool("STEPS_REQUIRE_PROOF", True)
STEPS_MAX_PER_ENTRY = int(env("STEPS_MAX_PER_ENTRY", "60000"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"core": {"handlers": ["console"], "level": "INFO"}},
}
