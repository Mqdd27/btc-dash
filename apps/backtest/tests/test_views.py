from unittest.mock import patch

import pytest

from apps.backtest.models import BacktestRun
from apps.backtest.services import run_backtest

from .test_services import seed_data, strategy_config, symbol  # noqa: F401


@pytest.mark.django_db
def test_list_view_renders(client, symbol, strategy_config):  # noqa: F811
    response = client.get("/backtests/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_create_view_queues_and_dispatches_celery_task(client, symbol, strategy_config):  # noqa: F811
    seed_data(symbol)

    with patch("apps.backtest.views.run_backtest_task.delay") as mock_delay:
        response = client.post("/backtests/create/", {
            "strategy": strategy_config.id, "symbol": symbol.id, "timeframe": "1h",
            "start_date": "2024-01-01", "end_date": "2024-01-01",
            "initial_capital": 10000, "fee": 0.0004, "slippage_percent": 0.0005,
            "position_size_type": "percentage_of_equity", "risk_per_trade": 0.01,
        })

    assert response.status_code == 302
    backtest = BacktestRun.objects.get()
    assert backtest.status == BacktestRun.Status.QUEUED
    mock_delay.assert_called_once_with(backtest.id)


@pytest.mark.django_db
def test_detail_view_shows_charts_only_when_completed(client, symbol, strategy_config):  # noqa: F811
    start, end = seed_data(symbol)
    backtest = run_backtest(strategy_config, symbol, "1h", start, end, initial_capital=10000)

    response = client.get(f"/backtests/{backtest.id}/")

    assert response.status_code == 200
    assert b"chart-price" in response.content


@pytest.mark.django_db
def test_trades_partial_filters_by_side(client, symbol, strategy_config):  # noqa: F811
    start, end = seed_data(symbol)
    backtest = run_backtest(strategy_config, symbol, "1h", start, end, initial_capital=10000)

    # seed_data only ever triggers LONG signals, so filtering by SHORT must be empty.
    response = client.get(f"/backtests/{backtest.id}/trades/", {"side": "SHORT"})

    assert response.status_code == 200
    assert b"No trades match these filters." in response.content


@pytest.mark.django_db
def test_compare_view_renders(client, symbol, strategy_config):  # noqa: F811
    response = client.get("/backtests/compare/")
    assert response.status_code == 200
