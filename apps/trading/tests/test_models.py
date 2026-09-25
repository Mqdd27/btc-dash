import pytest

from apps.trading.models import EngineConfig
from apps.trading.services import get_engine_config


@pytest.mark.django_db
def test_engine_config_safety_defaults():
    config = EngineConfig.objects.create()
    assert config.enabled is False
    assert config.execution_mode == EngineConfig.ExecutionMode.DISABLED


@pytest.mark.django_db
def test_get_engine_config_creates_singleton():
    first = get_engine_config()
    second = get_engine_config()
    assert first.pk == second.pk == 1
