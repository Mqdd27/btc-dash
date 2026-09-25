"""Event-driven backtest engine. Pure Python, no Django/DB -- candles + signals in,
trades + an equity curve out. Deterministic: no randomness anywhere, so the same
inputs always produce the same trades.

Execution model (documented assumptions):
- A signal generated from candle N executes no earlier than candle N+1's open.
  This is enforced structurally: signals are only checked against the candle
  immediately following their timestamp, never their own candle.
- Slippage always works against the trader: buy fills are marked up, sell fills
  are marked down, on both entries and exits.
- All fills (entry, SL, TP, forced end-of-data close) are treated as taker fills.
  maker_fee is accepted in config for a future limit-order model but unused here
  -- this engine has no resting-order book, only market-style fills.
- If both SL and TP fall inside the same candle's [low, high] range, the true
  intrabar order is unknowable from OHLC alone. We assume SL is hit first (the
  conservative assumption the task explicitly requires -- never assume the
  favorable outcome).
- Equity only changes when a trade closes (realized PnL), not via intrabar
  mark-to-market of open positions. The equity curve is therefore a step
  function over trade-close events, which is what position sizing and drawdown
  are computed from.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CandleBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SignalInput:
    timestamp: datetime
    side: str  # "LONG" | "SHORT"
    stop_loss: float
    take_profit: float


@dataclass(frozen=True)
class BacktestEngineConfig:
    initial_capital: float
    position_size_type: str = "percentage_of_equity"  # | "fixed_cash"
    risk_per_trade: float = 0.01
    maker_fee: float = 0.0002
    taker_fee: float = 0.0004
    slippage_percent: float = 0.0005
    allow_long: bool = True
    allow_short: bool = True
    maximum_simultaneous_positions: int = 1


@dataclass
class Trade:
    side: str
    signal_timestamp: datetime
    entry_timestamp: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float
    exit_timestamp: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    fees: float = 0.0
    slippage: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    return_pct: float = 0.0
    equity_after: float | None = None


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float


@dataclass
class OpenPosition:
    side: str
    signal_timestamp: datetime
    entry_timestamp: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float
    entry_fee: float
    entry_slippage: float


def position_size(entry_price: float, stop_loss: float, equity: float, config: BacktestEngineConfig) -> float:
    risk_amount = (
        config.risk_per_trade if config.position_size_type == "fixed_cash" else equity * config.risk_per_trade
    )
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return 0.0
    return risk_amount / stop_distance


def fill_price(reference_price: float, slippage_percent: float, is_buy: bool) -> float:
    sign = 1 if is_buy else -1
    return reference_price * (1 + sign * slippage_percent)


def run_engine(
    candles: list[CandleBar], signals: list[SignalInput], config: BacktestEngineConfig
) -> tuple[list[Trade], list[EquityPoint]]:
    signals_by_timestamp = {s.timestamp: s for s in signals}
    open_positions: list[OpenPosition] = []
    closed_trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []
    equity = config.initial_capital

    for i, candle in enumerate(candles):
        # 1. Entries: a signal on the previous candle executes at this candle's open.
        if i > 0:
            signal = signals_by_timestamp.get(candles[i - 1].timestamp)
            if signal is not None and len(open_positions) < config.maximum_simultaneous_positions:
                if (signal.side == "LONG" and config.allow_long) or (
                    signal.side == "SHORT" and config.allow_short
                ):
                    is_buy = signal.side == "LONG"
                    entry_price = fill_price(candle.open, config.slippage_percent, is_buy)
                    size = position_size(entry_price, signal.stop_loss, equity, config)
                    if size > 0:
                        entry_fee = entry_price * size * config.taker_fee
                        entry_slippage = abs(entry_price - candle.open) * size
                        open_positions.append(
                            OpenPosition(
                                side=signal.side,
                                signal_timestamp=signal.timestamp,
                                entry_timestamp=candle.timestamp,
                                entry_price=entry_price,
                                stop_loss=signal.stop_loss,
                                take_profit=signal.take_profit,
                                size=size,
                                entry_fee=entry_fee,
                                entry_slippage=entry_slippage,
                            )
                        )

        # 2. Exits: check SL/TP against this candle's range for every open position
        #    (including one that just entered on this same candle's open).
        still_open = []
        is_last_candle = i == len(candles) - 1
        for pos in open_positions:
            exit_reason, exit_level = check_exit(pos, candle, force_close=is_last_candle)
            if exit_reason is None:
                still_open.append(pos)
                continue
            trade = close_position(pos, candle.timestamp, exit_level, exit_reason, config, equity)
            equity = trade.equity_after
            closed_trades.append(trade)
        open_positions = still_open

        equity_curve.append(EquityPoint(timestamp=candle.timestamp, equity=equity))

    return closed_trades, equity_curve


def check_exit(pos: OpenPosition, candle: CandleBar, force_close: bool):
    if pos.side == "LONG":
        hit_sl = candle.low <= pos.stop_loss
        hit_tp = candle.high >= pos.take_profit
    else:
        hit_sl = candle.high >= pos.stop_loss
        hit_tp = candle.low <= pos.take_profit

    if hit_sl:
        return "stop_loss", pos.stop_loss  # conservative: SL wins on same-candle collision
    if hit_tp:
        return "take_profit", pos.take_profit
    if force_close:
        return "end_of_data", candle.close
    return None, None


def close_position(
    pos: OpenPosition, exit_timestamp, exit_level: float, exit_reason: str, config: BacktestEngineConfig, equity: float
) -> Trade:
    is_buy_to_close = pos.side == "SHORT"  # long exits by selling, short exits by buying back
    exit_price = fill_price(exit_level, config.slippage_percent, is_buy_to_close)
    exit_fee = exit_price * pos.size * config.taker_fee
    exit_slippage = abs(exit_price - exit_level) * pos.size

    if pos.side == "LONG":
        gross_pnl = (exit_price - pos.entry_price) * pos.size
    else:
        gross_pnl = (pos.entry_price - exit_price) * pos.size

    fees = pos.entry_fee + exit_fee
    net_pnl = gross_pnl - fees
    notional = pos.entry_price * pos.size
    return_pct = (net_pnl / notional * 100) if notional else 0.0

    return Trade(
        side=pos.side,
        signal_timestamp=pos.signal_timestamp,
        entry_timestamp=pos.entry_timestamp,
        entry_price=pos.entry_price,
        stop_loss=pos.stop_loss,
        take_profit=pos.take_profit,
        size=pos.size,
        exit_timestamp=exit_timestamp,
        exit_price=exit_price,
        exit_reason=exit_reason,
        fees=fees,
        slippage=pos.entry_slippage + exit_slippage,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        return_pct=return_pct,
        equity_after=equity + net_pnl,
    )
