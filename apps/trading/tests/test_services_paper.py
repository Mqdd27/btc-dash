from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from apps.market.models import Candle, MarketSymbol
from apps.trading.models import PaperAccount, PaperPosition, PaperTrade
from apps.trading.services import get_paper_account_stats

T0 = datetime(2024, 1, 1, tzinfo=dt_timezone.utc)


@pytest.fixture
def symbol(db):
    return MarketSymbol.objects.create(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", exchange="binance"
    )


@pytest.mark.django_db
def test_stats_reflect_realized_and_unrealized_pnl(symbol):
    account = PaperAccount.objects.create(initial_balance=10000, cash_balance=10100, equity=10100)

    closed = PaperPosition.objects.create(
        account=account, symbol=symbol, timeframe="1h", side="LONG", status=PaperPosition.Status.CLOSED,
        entry_timestamp=T0, entry_price=100, size=1, stop_loss=95, take_profit=110,
    )
    PaperTrade.objects.create(
        position=closed, exit_timestamp=T0 + timedelta(hours=1), exit_price=110,
        fees=1, pnl=100, return_pct=1.0, exit_reason="take_profit",
    )

    open_position = PaperPosition.objects.create(
        account=account, symbol=symbol, timeframe="1h", side="LONG", status=PaperPosition.Status.OPEN,
        entry_timestamp=T0, entry_price=100, size=2, stop_loss=95, take_profit=120,
    )
    Candle.objects.create(
        symbol=symbol, timeframe="1h", timestamp=T0, open=100, high=105, low=99, close=105,
        volume=1, closed=True,
    )

    stats = get_paper_account_stats()

    assert stats["realized_pnl"] == 100
    assert stats["unrealized_pnl"] == (105 - 100) * 2
    assert list(stats["open_positions"]) == [open_position]
    assert stats["win_rate_pct"] == 100.0
    assert stats["total_trades"] == 1


@pytest.mark.django_db
def test_stats_with_no_history_are_flat(symbol):
    stats = get_paper_account_stats()

    assert stats["realized_pnl"] == 0
    assert stats["unrealized_pnl"] == 0
    assert stats["win_rate_pct"] is None
    assert stats["profit_factor"] is None
    assert stats["max_drawdown_pct"] == 0
