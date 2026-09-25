from core.quant.strategy import EmaRsiStrategy, Signal, StrategyParams

PARAMS = StrategyParams(
    rsi_long_threshold=55, rsi_short_threshold=45, atr_sl_multiplier=1.5, atr_tp_multiplier=3.0
)


def signal(**overrides):
    kwargs = dict(close=100.0, ema_fast=20.0, ema_slow=10.0, rsi=60.0, atr=2.0, params=PARAMS)
    kwargs.update(overrides)
    return EmaRsiStrategy().generate_signal(**kwargs)


def test_long_condition():
    result = signal(ema_fast=20, ema_slow=10, rsi=60)  # ema_fast > ema_slow, rsi > 55
    assert result.side is Signal.LONG


def test_short_condition():
    result = signal(ema_fast=10, ema_slow=20, rsi=30)  # ema_fast < ema_slow, rsi < 45
    assert result.side is Signal.SHORT


def test_wait_condition_when_rules_disagree():
    # ema says long, rsi says neither long nor short threshold met
    result = signal(ema_fast=20, ema_slow=10, rsi=50)
    assert result.side is Signal.WAIT
    assert result.entry_reference_price is None


def test_wait_condition_when_indicators_not_warmed_up():
    result = signal(ema_fast=None)
    assert result.side is Signal.WAIT


def test_stop_loss_and_take_profit_for_long():
    result = signal(close=100.0, ema_fast=20, ema_slow=10, rsi=60, atr=2.0)
    assert result.entry_reference_price == 100.0
    assert result.stop_loss_reference == 100.0 - 1.5 * 2.0
    assert result.take_profit_reference == 100.0 + 3.0 * 2.0


def test_stop_loss_and_take_profit_for_short():
    result = signal(close=100.0, ema_fast=10, ema_slow=20, rsi=30, atr=2.0)
    assert result.entry_reference_price == 100.0
    assert result.stop_loss_reference == 100.0 + 1.5 * 2.0
    assert result.take_profit_reference == 100.0 - 3.0 * 2.0
