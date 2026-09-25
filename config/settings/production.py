from .base import *  # noqa: F401,F403

DEBUG = False

if SECRET_KEY == "insecure-dev-key-change-me":  # noqa: F405
    raise RuntimeError("Set DJANGO_SECRET_KEY before running in production.")

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
