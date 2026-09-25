# btc-dash / btc_trader

BTC quantitative trading research + paper-trading platform. This phase only
sets up the base architecture (Django + Postgres + Redis + Celery). No
trading, backtest, or ML logic yet.

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
and `execution_mode=disabled`. No order execution exists in this phase.
