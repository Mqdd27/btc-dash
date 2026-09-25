"""XGBoost training service: reads the train/validation CSVs build_ml_dataset
wrote, fits a model, and records a new ModelVersion. Chronological split only
-- train/validation/test come from fixed, non-overlapping date ranges (see
apps/ml/dataset.py DEFAULT_SPLITS), never a random shuffle.
"""

from pathlib import Path

import pandas as pd
from django.conf import settings
from django.utils import timezone
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from xgboost import XGBClassifier

from apps.market.models import MarketSymbol
from apps.strategy.models import StrategyConfig

from .dataset import ALL_FEATURE_COLUMNS, LABEL_COLUMN, load_split
from .models import ModelVersion

DEFAULT_HYPERPARAMETERS = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "eval_metric": "logloss",
    "early_stopping_rounds": 20,
}


def _classification_metrics(y_true, y_pred, y_proba) -> dict:
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "n_samples": len(y_true),
    }
    metrics["roc_auc"] = roc_auc_score(y_true, y_proba) if y_true.nunique() > 1 else None
    # Calibration: mean predicted probability vs. observed win rate per decile bucket.
    metrics["calibration"] = _calibration_table(y_true, y_proba)
    return metrics


def _calibration_table(y_true, y_proba, n_bins: int = 10) -> list[dict]:
    y_proba = pd.Series(y_proba).reset_index(drop=True)
    y_true = pd.Series(y_true).reset_index(drop=True)
    bins = pd.qcut(y_proba, q=min(n_bins, y_proba.nunique()), duplicates="drop")
    table = pd.DataFrame({"bucket": bins, "predicted": y_proba, "actual": y_true}).groupby(
        "bucket", observed=True
    ).agg(predicted_mean=("predicted", "mean"), actual_rate=("actual", "mean"), count=("actual", "size"))
    return table.reset_index(drop=True).to_dict("records")


def train_model(
    strategy_config: StrategyConfig,
    symbol: MarketSymbol,
    timeframe: str,
    name: str,
    hyperparameters: dict | None = None,
) -> ModelVersion:
    train_df = load_split(strategy_config, symbol, timeframe, "train")
    val_df = load_split(strategy_config, symbol, timeframe, "validation")
    if train_df.empty or val_df.empty:
        raise ValueError("train or validation split is empty -- check build_ml_dataset output.")

    hyperparameters = {**DEFAULT_HYPERPARAMETERS, **(hyperparameters or {})}
    X_train, y_train = train_df[ALL_FEATURE_COLUMNS], train_df[LABEL_COLUMN]
    X_val, y_val = val_df[ALL_FEATURE_COLUMNS], val_df[LABEL_COLUMN]

    model = XGBClassifier(**hyperparameters)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    y_pred = model.predict(X_val)
    y_proba = model.predict_proba(X_val)[:, 1]
    validation_metrics = _classification_metrics(y_val, y_pred, y_proba)

    model_dir = Path(settings.MEDIA_ROOT) / "ml" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / f"{name}_{timezone.now():%Y%m%d%H%M%S}.json"
    model.save_model(str(model_path))

    return ModelVersion.objects.create(
        name=name, algorithm="xgboost", strategy=strategy_config, symbol=symbol, timeframe=timeframe,
        training_start=train_df["signal_timestamp"].min(), training_end=train_df["signal_timestamp"].max(),
        features=ALL_FEATURE_COLUMNS, hyperparameters=hyperparameters,
        validation_metrics={"validation": validation_metrics},
        model_file=str(model_path.relative_to(settings.MEDIA_ROOT)),
        active=False,  # safety default -- must be explicitly activated
    )
