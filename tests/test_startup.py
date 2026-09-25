import django
from django.conf import settings


def test_django_settings_configured():
    assert settings.configured


def test_django_setup_succeeds():
    django.setup()
