"""Pure rule-based strategy logic. No Django, no DB -- features/config in, a
decision out. Callers (apps/strategy/services.py) are responsible for only ever
passing in a feature snapshot computed from data at or before the signal candle;
this layer has no notion of "future" data at all, so it can't leak it.
"""

from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"


@dataclass(frozen=True)
class StrategyParams:
    rsi_long_threshold: float
    rsi_short_threshold: float
    atr_sl_multiplier: float
    atr_tp_multiplier: float


@dataclass(frozen=True)
class SignalResult:
    side: Signal
    # Reference price at the close of the signal candle -- not a fill price.
    # The backtest engine executes at the next candle's realistic entry point,
    # never at this reference.
    entry_reference_price: float | None = None
    stop_loss_reference: float | None = None
    take_profit_reference: float | None = None


class BaseStrategy:
    version = "1"

    def generate_signal(self, *, close, ema_fast, ema_slow, rsi, atr, params: StrategyParams) -> SignalResult:
        raise NotImplementedError


class EmaRsiStrategy(BaseStrategy):
    version = "1"

    def generate_signal(self, *, close, ema_fast, ema_slow, rsi, atr, params: StrategyParams) -> SignalResult:
        if None in (close, ema_fast, ema_slow, rsi, atr):
            return SignalResult(Signal.WAIT)  # indicators not warmed up yet

        if ema_fast > ema_slow and rsi > params.rsi_long_threshold:
            side = Signal.LONG
        elif ema_fast < ema_slow and rsi < params.rsi_short_threshold:
            side = Signal.SHORT
        else:
            return SignalResult(Signal.WAIT)

        sl_distance = params.atr_sl_multiplier * atr
        tp_distance = params.atr_tp_multiplier * atr
        if side is Signal.LONG:
            stop_loss, take_profit = close - sl_distance, close + tp_distance
        else:
            stop_loss, take_profit = close + sl_distance, close - tp_distance

        return SignalResult(side, close, stop_loss, take_profit)
