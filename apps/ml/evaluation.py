"""Evaluation: classification metrics on the held-out test split, plus the
comparison that actually matters -- trading baseline (every candidate) vs.
baseline + XGBoost probability filter, on the same test-period candles.
"""

from apps.backtest.services import DEFAULT_ENGINE_CONFIG, load_candle_bars, load_signal_inputs
from core.quant.backtest import BacktestEngineConfig, run_engine
from core.quant.metrics import compute_metrics

from .dataset import ALL_FEATURE_COLUMNS, LABEL_COLUMN, load_split
from .models import ModelVersion
from .prediction import DEFAULT_WIN_PROBABILITY_THRESHOLD, load_model

TRADING_METRIC_KEYS = ["total_return_pct", "final_capital", "profit_factor", "max_drawdown_pct", "sharpe_ratio", "total_trades"]


def evaluate_model(
    model_version: ModelVersion, threshold: float = DEFAULT_WIN_PROBABILITY_THRESHOLD
) -> dict:
    test_df = load_split(model_version.strategy, model_version.symbol, model_version.timeframe, "test")
    if test_df.empty:
        raise ValueError("test split is empty -- check build_ml_dataset output.")

    model = load_model(model_version)
    X_test, y_test = test_df[ALL_FEATURE_COLUMNS], test_df[LABEL_COLUMN]
    proba = model.predict_proba(X_test)[:, 1]
    y_pred = (proba >= 0.5).astype(int)

    from .training import _classification_metrics  # local import: avoids a training<->evaluation cycle at module load

    classification_metrics = _classification_metrics(y_test, y_pred, proba)

    test_start = test_df["signal_timestamp"].min().to_pydatetime()
    test_end = test_df["signal_timestamp"].max().to_pydatetime()
    trading_comparison = _compare_trading_performance(model_version, test_df, proba, threshold, test_start, test_end)

    model_version.validation_metrics = {
        **(model_version.validation_metrics or {}),
        "test": classification_metrics,
        "trading_comparison": trading_comparison,
    }
    model_version.save(update_fields=["validation_metrics"])
    return model_version.validation_metrics


def _compare_trading_performance(model_version, test_df, proba, threshold, start, end) -> dict:
    candles = load_candle_bars(model_version.symbol, model_version.timeframe, start, end)
    all_signals = load_signal_inputs(model_version.strategy, model_version.symbol, model_version.timeframe, start, end)
    engine_config = BacktestEngineConfig(initial_capital=10000, **DEFAULT_ENGINE_CONFIG)

    passing_timestamps = {
        ts.to_pydatetime() for ts in test_df.loc[proba >= threshold, "signal_timestamp"]
    }
    filtered_signals = [s for s in all_signals if s.timestamp in passing_timestamps]

    baseline_trades, _ = run_engine(candles, all_signals, engine_config)
    filtered_trades, _ = run_engine(candles, filtered_signals, engine_config)

    baseline_metrics = compute_metrics(baseline_trades, initial_capital=10000)
    filtered_metrics = compute_metrics(filtered_trades, initial_capital=10000)

    return {
        "threshold": threshold,
        "baseline": {k: baseline_metrics[k] for k in TRADING_METRIC_KEYS},
        "filtered": {k: filtered_metrics[k] for k in TRADING_METRIC_KEYS},
    }
