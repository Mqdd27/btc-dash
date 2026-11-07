# btc-dash / btc_trader

[![CI](https://github.com/Mqdd27/btc-dash/actions/workflows/ci.yml/badge.svg)](https://github.com/Mqdd27/btc-dash/actions/workflows/ci.yml)

BTC quantitative trading research + paper-trading platform (Django + Postgres +
Redis + Celery). It pulls BTCUSDT market data from Binance, builds features,
generates baseline strategy signals, backtests them, filters them with an
XGBoost win-probability model (validated walk-forward), and runs a
candle-close-driven engine that records live signals and simulates them on a
virtual paper account. An optional Claude-based AI reviewer can sit on top.
No real orders are ever sent to an exchange.

Full usage guide (dashboard, backtests, walk-forward, AI agents, admin, CLI
workflow): [docs/USAGE.md](docs/USAGE.md).

## Modules

- `apps/market` -- Binance candles, funding rate and open interest via ccxt, plus technical/derivatives feature snapshots.
- `apps/strategy` -- EMA/RSI baseline strategy that turns feature snapshots into signal candidates with ATR-based SL/TP.
- `apps/backtest` -- backtest runs (fees, slippage, sizing, SL/TP) with trade list, metrics and run comparison, executed via Celery.
- `apps/ml` -- ML dataset from backtest outcomes, XGBoost training/evaluation, and walk-forward validation.
- `apps/trading` -- live engine (`EngineConfig`, `LiveSignal`) evaluated on each candle close, plus virtual paper trading.
- `apps/agents` -- optional Claude AI reviewer (`quant_ai`) and multi-agent TradingAgents pipeline (`full_agent`), with daily call limit and caching.
- `apps/dashboard` -- dashboard UI, live signal panel and health checks.

## Setup

```bash
pyenv install 3.12.13   # if not already installed
pyenv local 3.12.13
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/development.txt

cp .env.example .env    # edit as needed

createdb btc_trader     # requires local PostgreSQL

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Visit http://localhost:8000/ for the dashboard, http://localhost:8000/admin/
for Django admin.

## Running services

```bash
# Django dev server
python manage.py runserver

# Redis (required for Celery broker/result backend)
redis-server

# Celery worker
celery -A config worker -l info

# Celery beat (scheduler)
celery -A config beat -l info
```

## Tests

```bash
pytest
```

## Engine safety default

`EngineConfig` (Django admin → Trading) always starts with `enabled=False`
and `execution_mode=disabled`. Paper trading (`execution_mode=paper`) is
purely virtual and never touches a real exchange. `live` exists as a choice
but is not implemented, and the dashboard refuses to set it. The AI reviewer
is also off by default (`AI_ENABLED=False`).
