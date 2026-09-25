"""Paper trading engine. Reuses the exact same fee/slippage/sizing/SL-TP-collision
primitives as the backtest engine (core/quant/backtest.py) -- same assumptions,
just driven incrementally by live candle closes instead of a historical batch.

Never touches a real exchange. Only runs at all when EngineConfig.execution_mode
is "paper" -- "live" is explicitly not implemented (see module docstring on
apps/trading/engine.py and the project-wide "no order execution" boundary).
"""

from apps.backtest.services import DEFAULT_ENGINE_CONFIG
from apps.market.models import Candle
from core.quant.backtest import (
    BacktestEngineConfig, CandleBar, OpenPosition, check_exit, close_position, fill_price, position_size,
)

from .models import EngineConfig, LiveSignal, PaperAccount, PaperPosition, PaperTrade


def get_paper_account() -> PaperAccount:
    account, _ = PaperAccount.objects.get_or_create(pk=1)
    return account


def advance_paper_trading(engine_config: EngineConfig, candle: Candle, live_signal: LiveSignal) -> None:
    """Called once per live evaluation, right after the LiveSignal for this
    candle is created. Order matters, mirroring the backtest engine's per-candle
    loop: fill anything queued on the previous candle first, then check exits
    against this candle's range, then queue any new signal for the *next* one.
    """
    if engine_config.execution_mode != EngineConfig.ExecutionMode.PAPER:
        return

    account = get_paper_account()
    config = BacktestEngineConfig(initial_capital=account.cash_balance, **DEFAULT_ENGINE_CONFIG)
    bar = CandleBar(
        timestamp=candle.timestamp, open=float(candle.open), high=float(candle.high),
        low=float(candle.low), close=float(candle.close),
    )

    _fill_pending_positions(account, candle.symbol, engine_config.timeframe, bar, config)
    _check_open_positions(account, candle.symbol, engine_config.timeframe, bar, config)

    if not account.paused and live_signal.decision in (LiveSignal.Side.LONG, LiveSignal.Side.SHORT):
        _queue_new_position(account, candle.symbol, engine_config.timeframe, live_signal)

    account.equity = account.cash_balance + unrealized_pnl(account)
    account.save(update_fields=["equity"])


def _fill_pending_positions(account, symbol, timeframe, bar: CandleBar, config: BacktestEngineConfig):
    pending = PaperPosition.objects.filter(
        account=account, symbol=symbol, timeframe=timeframe, status=PaperPosition.Status.PENDING
    )
    open_count = PaperPosition.objects.filter(
        account=account, symbol=symbol, timeframe=timeframe, status=PaperPosition.Status.OPEN
    ).count()

    for pending_position in pending:
        if open_count >= config.maximum_simultaneous_positions:
            break
        is_buy = pending_position.side == PaperPosition.Side.LONG
        entry_price = fill_price(bar.open, config.slippage_percent, is_buy)
        size = position_size(entry_price, pending_position.stop_loss, account.cash_balance, config)
        if size <= 0:
            pending_position.delete()  # can't size it (degenerate SL) -- don't leave it stuck pending forever
            continue

        pending_position.entry_timestamp = bar.timestamp
        pending_position.entry_price = entry_price
        pending_position.size = size
        pending_position.entry_fee = entry_price * size * config.taker_fee
        pending_position.entry_slippage = abs(entry_price - bar.open) * size
        pending_position.status = PaperPosition.Status.OPEN
        pending_position.save()
        open_count += 1


def _check_open_positions(account, symbol, timeframe, bar: CandleBar, config: BacktestEngineConfig):
    open_positions = PaperPosition.objects.filter(
        account=account, symbol=symbol, timeframe=timeframe, status=PaperPosition.Status.OPEN
    )
    for position in open_positions:
        exit_reason, exit_level = check_exit(_to_open_position(position), bar, force_close=False)
        if exit_reason is None:
            continue  # strategy-defined exit: this strategy only exits via SL/TP, so nothing else to check here

        trade = close_position(_to_open_position(position), bar.timestamp, exit_level, exit_reason, config, account.cash_balance)
        account.cash_balance = trade.equity_after
        account.save(update_fields=["cash_balance"])

        position.status = PaperPosition.Status.CLOSED
        position.save(update_fields=["status"])
        PaperTrade.objects.create(
            position=position, exit_timestamp=trade.exit_timestamp, exit_price=trade.exit_price,
            fees=trade.fees, pnl=trade.net_pnl, return_pct=trade.return_pct, exit_reason=trade.exit_reason,
        )


def _queue_new_position(account, symbol, timeframe, live_signal: LiveSignal):
    PaperPosition.objects.create(
        account=account, symbol=symbol, timeframe=timeframe, side=live_signal.decision,
        status=PaperPosition.Status.PENDING, signal=live_signal,
        stop_loss=live_signal.stop_loss, take_profit=live_signal.take_profit,
    )


def _to_open_position(position: PaperPosition) -> OpenPosition:
    return OpenPosition(
        side=position.side, signal_timestamp=position.created_at, entry_timestamp=position.entry_timestamp,
        entry_price=position.entry_price, stop_loss=position.stop_loss, take_profit=position.take_profit,
        size=position.size, entry_fee=position.entry_fee, entry_slippage=position.entry_slippage,
    )


def unrealized_pnl(account) -> float:
    total = 0.0
    open_positions = PaperPosition.objects.filter(account=account, status=PaperPosition.Status.OPEN)
    for position in open_positions:
        last_close = (
            Candle.objects.filter(symbol=position.symbol, timeframe=position.timeframe, closed=True)
            .order_by("-timestamp").values_list("close", flat=True).first()
        )
        if last_close is None:
            continue
        last_close = float(last_close)
        if position.side == PaperPosition.Side.LONG:
            total += (last_close - position.entry_price) * position.size
        else:
            total += (position.entry_price - last_close) * position.size
    return total
