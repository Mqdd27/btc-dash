#!/usr/bin/env bash
# Builds the ML dataset and trains the XGBoost win-probability model. ema_rsi/BTCUSDT only.
# Usage: scripts/train_model.sh <timeframe>
# e.g.:  scripts/train_model.sh 1h
set -euo pipefail

STRATEGY="ema_rsi"
SYMBOL="BTCUSDT"
TIMEFRAME="${1:?usage: train_model.sh <timeframe>}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate

python manage.py build_ml_dataset --strategy "$STRATEGY" --symbol "$SYMBOL" --timeframe "$TIMEFRAME"
python manage.py train_quant_model --strategy "$STRATEGY" --symbol "$SYMBOL" --timeframe "$TIMEFRAME"
