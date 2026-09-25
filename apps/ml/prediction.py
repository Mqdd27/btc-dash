"""Inference: load a saved XGBoost model and score feature rows."""

from pathlib import Path

import pandas as pd
from django.conf import settings
from xgboost import XGBClassifier

from apps.market.models import MarketSymbol
from apps.strategy.models import StrategyConfig

from .dataset import ALL_FEATURE_COLUMNS
from .models import ModelVersion

DEFAULT_WIN_PROBABILITY_THRESHOLD = 0.65


def load_model(model_version: ModelVersion) -> XGBClassifier:
    model = XGBClassifier()
    model.load_model(str(Path(settings.MEDIA_ROOT) / model_version.model_file))
    return model


def get_active_model_version(
    strategy_config: StrategyConfig, symbol: MarketSymbol, timeframe: str
) -> ModelVersion | None:
    return ModelVersion.objects.filter(
        strategy=strategy_config, symbol=symbol, timeframe=timeframe, active=True
    ).order_by("-created_at").first()


def predict_win_probability(model_version: ModelVersion, features: pd.DataFrame) -> pd.Series:
    """features must have all of ALL_FEATURE_COLUMNS. Returns P(win) per row."""
    model = load_model(model_version)
    # A column that's None for every row in `features` (e.g. funding/open interest
    # before that data existed) infers as object dtype, which XGBoost rejects outright.
    # Same fix as apps/ml/dataset.py::build_split_dataset -- cast here too since every
    # caller builds its own small ad-hoc DataFrame.
    x = features[ALL_FEATURE_COLUMNS].astype(float)
    return pd.Series(model.predict_proba(x)[:, 1], index=features.index)
