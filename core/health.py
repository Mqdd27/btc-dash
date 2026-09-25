"""Infra connectivity checks shared by the dashboard and /health/ endpoints."""

from django.conf import settings
from django.db import connection


def check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


def check_redis() -> bool:
    import redis

    try:
        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping()
        return True
    except Exception:
        return False


def celery_configured() -> bool:
    return bool(settings.CELERY_BROKER_URL)
