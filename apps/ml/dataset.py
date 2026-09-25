"""ML dataset builder: joins backtest-engine trade outcomes back to the exact
feature snapshot that was available when each signal fired, and labels each
row WIN/LOSS from the trade's actual realized PnL.

No leakage: features come only from FeatureSnapshot (already causal by
construction, see core/features/indicators.py), side comes from the signal
itself, and the label comes from BacktestTrade.net_pnl -- which is never
included as a feature, only used to derive the target column.
"""

from datetime import datetime, timezone as dt_timezone
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.utils import timezone

from apps.backtest.services import load_candle_bars, load_signal_inputs
from apps.market.models import MarketSymbol
from apps.strategy.models import SignalCandidate, StrategyConfig
from apps.strategy.services import generate_signals
from core.quant.backtest import BacktestEngineConfig, Trade, run_engine

# Maps 1:1 onto the "possible input features" list in the spec, using the
# normalized/ratio FeatureSnapshot columns (percent distances, not raw EMA
# price levels) wherever one exists, since BTC's price scale itself is not
# stationary across a 2021-2026 training window.
FEATURE_COLUMNS = [
    "rsi_14",
    "distance_close_ema20", "distance_close_ema50", "distance_close_ema200",
    "ema20_vs_ema50", "ema50_vs_ema200",
    "macd", "macd_signal", "macd_histogram",
    "atr_14", "atr_percent",
    "rolling_volatility",
    "volume_sma", "volume_change", "volume_zscore",
    "funding_rate", "funding_rate_change",
    "open_interest", "open_interest_change",
    "return_1", "return_4", "return_24",
    "candle_body_percent", "upper_wick_percent", "lower_wick_percent",
]
SIDE_COLUMN = "is_long"
ALL_FEATURE_COLUMNS = FEATURE_COLUMNS + [SIDE_COLUMN]
LABEL_COLUMN = "label"

DEFAULT_SPLITS = {
    "train": ("2021-01-01", "2023-12-31"),
    "validation": ("2024-01-01", "2024-12-31"),
    "test": ("2025-01-01", None),  # None end = "through available data" (now)
}


def get_labeled_trades(
    strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, start, end
) -> list[Trade]:
    """Runs the real engine over [start, end] without persisting a BacktestRun --
    we only need the resulting trades transiently, to build training rows."""
    generate_signals(strategy_config, symbol, timeframe, start, end)  # idempotent
    candles = load_candle_bars(symbol, timeframe, start, end)
    signals = load_signal_inputs(strategy_config, symbol, timeframe, start, end)
    trades, _equity_curve = run_engine(candles, signals, BacktestEngineConfig(initial_capital=10000))
    return trades


def build_split_dataset(
    strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, start, end
) -> pd.DataFrame:
    trades = get_labeled_trades(strategy_config, symbol, timeframe, start, end)
    closed = [t for t in trades if t.exit_timestamp is not None]
    if not closed:
        return pd.DataFrame(columns=["signal_timestamp", *ALL_FEATURE_COLUMNS, LABEL_COLUMN])

    signals_by_ts = {
        sc.candle_timestamp: sc
        for sc in SignalCandidate.objects.filter(
            strategy=strategy_config, symbol=symbol, timeframe=timeframe,
            candle_timestamp__in=[t.signal_timestamp for t in closed],
        ).select_related("feature_snapshot")
    }

    rows = []
    for t in closed:
        candidate = signals_by_ts.get(t.signal_timestamp)
        if candidate is None or candidate.feature_snapshot is None:
            continue
        fs = candidate.feature_snapshot
        row = {col: getattr(fs, col) for col in FEATURE_COLUMNS}
        row[SIDE_COLUMN] = 1 if t.side == "LONG" else 0
        row[LABEL_COLUMN] = 1 if t.net_pnl > 0 else 0
        row["signal_timestamp"] = t.signal_timestamp
        rows.append(row)

    df = pd.DataFrame(rows, columns=["signal_timestamp", *ALL_FEATURE_COLUMNS, LABEL_COLUMN])
    # A feature that's None for every row in this window (e.g. before enough
    # candles exist for EMA warm-up, or before funding data was collected)
    # otherwise ends up as pandas "object" dtype, which XGBoost rejects outright.
    df[ALL_FEATURE_COLUMNS] = df[ALL_FEATURE_COLUMNS].astype(float)
    return df


def dataset_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / "ml" / "datasets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dataset_path(strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, split: str) -> Path:
    return dataset_dir() / f"{strategy_config.name}_{symbol.symbol}_{timeframe}_{split}.csv"


def build_ml_dataset(
    strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, splits: dict | None = None
) -> dict[str, Path]:
    """Builds and writes train/validation/test CSVs to disk. Returns their paths."""
    splits = splits or DEFAULT_SPLITS
    written = {}
    for name, (start_str, end_str) in splits.items():
        start = datetime.fromisoformat(start_str).replace(tzinfo=dt_timezone.utc)
        end = datetime.fromisoformat(end_str).replace(tzinfo=dt_timezone.utc) if end_str else timezone.now()
        df = build_split_dataset(strategy_config, symbol, timeframe, start, end)
        path = dataset_path(strategy_config, symbol, timeframe, name)
        df.to_csv(path, index=False)
        written[name] = path
    return written


def load_split(strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str, split: str) -> pd.DataFrame:
    path = dataset_path(strategy_config, symbol, timeframe, split)
    if not path.exists():
        raise FileNotFoundError(f"No '{split}' dataset at {path} -- run build_ml_dataset first.")
    return pd.read_csv(path, parse_dates=["signal_timestamp"])
