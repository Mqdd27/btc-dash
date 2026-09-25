"""Walk-forward validation orchestration: for each window, train a fresh
model on that window's training range only, predict on its (strictly later)
test range, simulate the probability-filtered trades, and store metrics.
Aggregate performance is computed strictly from the concatenation of every
window's test-period trades -- training-period performance never enters it.
"""

from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.backtest.services import DEFAULT_ENGINE_CONFIG, load_candle_bars, load_signal_inputs
from apps.market.models import MarketSymbol
from apps.strategy.models import StrategyConfig
from core.quant.backtest import BacktestEngineConfig, run_engine
from core.quant.metrics import compute_metrics
from core.quant.walk_forward import generate_windows

from .dataset import ALL_FEATURE_COLUMNS, LABEL_COLUMN, build_split_dataset
from .models import WalkForwardRun, WalkForwardWindow
from .prediction import DEFAULT_WIN_PROBABILITY_THRESHOLD
from .training import DEFAULT_HYPERPARAMETERS, fit_xgboost


def run_walk_forward(
    strategy_config: StrategyConfig,
    symbol: MarketSymbol,
    timeframe: str,
    start,
    end,
    mode: str,
    training_months: int = 24,
    test_months: int = 3,
    retrain_months: int = 3,
    threshold: float = DEFAULT_WIN_PROBABILITY_THRESHOLD,
    hyperparameters: dict | None = None,
) -> WalkForwardRun:
    hyperparameters = DEFAULT_HYPERPARAMETERS | (hyperparameters or {})
    run = WalkForwardRun.objects.create(
        strategy=strategy_config, symbol=symbol, timeframe=timeframe, mode=mode,
        start_date=start, end_date=end, training_months=training_months,
        test_months=test_months, retrain_months=retrain_months,
        probability_threshold=threshold, hyperparameters=hyperparameters,
        status=WalkForwardRun.Status.RUNNING,
    )

    try:
        windows = generate_windows(start, end, mode, training_months, test_months, retrain_months)
        model_dir = Path(settings.MEDIA_ROOT) / "ml" / "walk_forward"
        model_dir.mkdir(parents=True, exist_ok=True)

        all_test_trades = []
        for w in windows:
            train_df = build_split_dataset(strategy_config, symbol, timeframe, w.train_start, w.train_end)
            if train_df.empty or train_df[LABEL_COLUMN].nunique() < 2:
                continue  # not enough signal in this window to train on -- skip, don't fabricate

            model = fit_xgboost(train_df, val_df=None, hyperparameters=hyperparameters)
            model_path = model_dir / f"run{run.id}_window{w.index}.json"
            model.save_model(str(model_path))

            window_trades = _simulate_test_window(model, strategy_config, symbol, timeframe, w, threshold)
            all_test_trades.extend(window_trades)

            WalkForwardWindow.objects.create(
                run=run, index=w.index, train_start=w.train_start, train_end=w.train_end,
                test_start=w.test_start, test_end=w.test_end,
                model_file=str(model_path.relative_to(settings.MEDIA_ROOT)),
                metrics=compute_metrics(window_trades, initial_capital=10000),
            )

        all_test_trades.sort(key=lambda t: t.entry_timestamp)
        run.aggregate_metrics = compute_metrics(all_test_trades, initial_capital=10000)
        run.status = WalkForwardRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.save(update_fields=["aggregate_metrics", "status", "completed_at"])
    except Exception:
        run.status = WalkForwardRun.Status.FAILED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at"])
        raise

    return run


def _simulate_test_window(model, strategy_config, symbol, timeframe, window, threshold):
    """Predicts on the test window's own signals (never seen in training) and
    simulates trades using only the ones the model rates >= threshold."""
    test_df = build_split_dataset(strategy_config, symbol, timeframe, window.test_start, window.test_end)
    candles = load_candle_bars(symbol, timeframe, window.test_start, window.test_end)
    all_signals = load_signal_inputs(strategy_config, symbol, timeframe, window.test_start, window.test_end)

    if test_df.empty:
        passing_timestamps = set()
    else:
        proba = model.predict_proba(test_df[ALL_FEATURE_COLUMNS])[:, 1]
        passing_timestamps = {ts.to_pydatetime() for ts in test_df.loc[proba >= threshold, "signal_timestamp"]}

    filtered_signals = [s for s in all_signals if s.timestamp in passing_timestamps]
    engine_config = BacktestEngineConfig(initial_capital=10000, **DEFAULT_ENGINE_CONFIG)
    trades, _equity_curve = run_engine(candles, filtered_signals, engine_config)
    return trades
