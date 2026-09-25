#!/usr/bin/env bash
# Starts everything btc-dash needs for local dev: Redis, Celery worker, Celery
# beat, and the Django dev server. Postgres runs as a persistent brew service
# already (`brew services list`) so it's only checked here, never started.
#
# Ctrl+C stops the dev server and cleans up the worker/beat/redis this script
# started. Anything already running before this script ran is left alone.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate

LOG_DIR="/tmp/btc-dash-dev"
mkdir -p "$LOG_DIR"

STARTED_REDIS=0
WORKER_PID=""
BEAT_PID=""
SERVER_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
    [[ -n "$WORKER_PID" ]] && kill "$WORKER_PID" 2>/dev/null || true
    [[ -n "$BEAT_PID" ]] && kill "$BEAT_PID" 2>/dev/null || true
    if [[ "$STARTED_REDIS" == "1" ]]; then
        redis-cli shutdown 2>/dev/null || true
    fi
}
# Trap INT/TERM explicitly, not just EXIT -- runserver runs as a background
# child we `wait` on, so a signal sent to this script's PID needs its own
# handler to actually propagate the shutdown instead of just ending `wait`.
trap cleanup INT TERM EXIT

# --- Postgres: must already be running (brew services / manual). ---
if ! pg_isready -q 2>/dev/null; then
    echo "Postgres isn't reachable. Start it first: brew services start postgresql@14"
    exit 1
fi
echo "Postgres: OK"

# --- Redis: start it if nothing is already listening on 6379. ---
if redis-cli ping >/dev/null 2>&1; then
    echo "Redis: already running"
else
    echo "Redis: starting..."
    /opt/homebrew/opt/redis/bin/redis-server /opt/homebrew/etc/redis.conf --daemonize no \
        > "$LOG_DIR/redis.log" 2>&1 &
    disown
    STARTED_REDIS=1
    for _ in $(seq 1 20); do
        redis-cli ping >/dev/null 2>&1 && break
        sleep 0.5
    done
    redis-cli ping >/dev/null 2>&1 || { echo "Redis failed to start -- see $LOG_DIR/redis.log"; exit 1; }
fi

# --- Celery worker: --pool=solo is required on macOS (prefork crashes here). ---
echo "Celery worker: starting..."
celery -A config worker -l info --pool=solo > "$LOG_DIR/celery-worker.log" 2>&1 &
WORKER_PID=$!

# --- Celery beat: drives the live engine's candle-close check. ---
echo "Celery beat: starting..."
celery -A config beat -l info > "$LOG_DIR/celery-beat.log" 2>&1 &
BEAT_PID=$!

sleep 1
echo ""
echo "All services up. Logs in $LOG_DIR/"
echo "Dashboard: http://127.0.0.1:8000/"
echo "Press Ctrl+C to stop everything this script started."
echo ""

# Backgrounded + waited-on (not run directly in the foreground) so the INT/TERM
# trap above reliably fires and can clean up the worker/beat/redis it started.
python manage.py runserver &
SERVER_PID=$!
wait "$SERVER_PID"
