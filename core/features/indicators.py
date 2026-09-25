"""Pure feature-engineering math. No Django, no DB -- just a candle DataFrame in,
a feature DataFrame out. Every column here is computed with pandas rolling/ewm/diff
ops, which by construction only look at row T and earlier: no future data ever
reaches a row's value. Row order (ascending timestamp) matters -- callers must sort.
"""

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange, BollingerBands

RETURN_WINDOW = 20  # shared window for rolling volatility / volume SMA / z-score


def compute_technical_features(candles: pd.DataFrame) -> pd.DataFrame:
    """candles: columns [timestamp, open, high, low, close, volume], sorted ascending."""
    close, high, low, open_, volume = (
        candles["close"],
        candles["high"],
        candles["low"],
        candles["open"],
        candles["volume"],
    )

    out = pd.DataFrame(index=candles.index)
    out["timestamp"] = candles["timestamp"]

    out["return_1"] = close.pct_change(1)
    out["return_4"] = close.pct_change(4)
    out["return_24"] = close.pct_change(24)
    out["log_return"] = np.log(close / close.shift(1))

    for span in (10, 20, 50, 100, 200):
        out[f"ema_{span}"] = close.ewm(span=span, adjust=False).mean()

    out["rsi_14"] = RSIIndicator(close, window=14).rsi()

    macd = MACD(close)
    out["macd"] = macd.macd()
    out["macd_signal"] = macd.macd_signal()
    out["macd_histogram"] = macd.macd_diff()

    # ponytail: ta's AverageTrueRange indexes out of bounds when len(close) <= window,
    # so guard it explicitly instead of letting a short history crash the whole build.
    if len(close) > 14:
        out["atr_14"] = AverageTrueRange(high, low, close, window=14).average_true_range()
    else:
        out["atr_14"] = np.nan

    bb = BollingerBands(close, window=20, window_dev=2)
    out["bollinger_upper"] = bb.bollinger_hband()
    out["bollinger_middle"] = bb.bollinger_mavg()
    out["bollinger_lower"] = bb.bollinger_lband()
    out["bollinger_bandwidth"] = (out["bollinger_upper"] - out["bollinger_lower"]) / out["bollinger_middle"]

    out["rolling_volatility"] = out["log_return"].rolling(RETURN_WINDOW).std()
    out["volume_sma"] = volume.rolling(RETURN_WINDOW).mean()
    out["volume_change"] = volume.pct_change(1)
    vol_std = volume.rolling(RETURN_WINDOW).std()
    out["volume_zscore"] = (volume - out["volume_sma"]) / vol_std

    # derived
    out["distance_close_ema20"] = (close - out["ema_20"]) / out["ema_20"]
    out["distance_close_ema50"] = (close - out["ema_50"]) / out["ema_50"]
    out["distance_close_ema200"] = (close - out["ema_200"]) / out["ema_200"]
    out["ema20_vs_ema50"] = (out["ema_20"] - out["ema_50"]) / out["ema_50"]
    out["ema50_vs_ema200"] = (out["ema_50"] - out["ema_200"]) / out["ema_200"]
    out["atr_percent"] = out["atr_14"] / close
    out["candle_body_percent"] = (close - open_).abs() / open_
    out["upper_wick_percent"] = (high - pd.concat([open_, close], axis=1).max(axis=1)) / open_
    out["lower_wick_percent"] = (pd.concat([open_, close], axis=1).min(axis=1) - low) / open_

    return out.replace([np.inf, -np.inf], np.nan)


def attach_derivatives(features: pd.DataFrame, funding: pd.DataFrame, open_interest: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time asof-join: each row gets the latest funding/OI known at or
    before its timestamp -- never a value from after it (no forward-fill of the
    future, only of the past, which is exactly what merge_asof(direction="backward")
    guarantees).
    """
    result = features
    if not funding.empty:
        result = pd.merge_asof(
            result.sort_values("timestamp"),
            funding.sort_values("timestamp").rename(columns={"funding_rate": "funding_rate"}),
            on="timestamp",
            direction="backward",
        )
        result["funding_rate_change"] = result["funding_rate"].diff(1)
    else:
        result["funding_rate"] = np.nan
        result["funding_rate_change"] = np.nan

    if not open_interest.empty:
        result = pd.merge_asof(
            result.sort_values("timestamp"),
            open_interest.sort_values("timestamp"),
            on="timestamp",
            direction="backward",
        )
        result["open_interest_change"] = result["open_interest"].diff(1)
    else:
        result["open_interest"] = np.nan
        result["open_interest_change"] = np.nan

    return result
