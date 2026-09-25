from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand

from apps.market.features import build_features
from apps.market.services import resolve_market_symbol


class Command(BaseCommand):
    help = "Compute and store engineered features for a symbol/timeframe over a date range."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")
        parser.add_argument("--start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--end", required=True, help="YYYY-MM-DD")

    def handle(self, *args, **options):
        start = datetime.strptime(options["start"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
        end = datetime.strptime(options["end"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)

        symbol = resolve_market_symbol(options["symbol"])
        count = build_features(symbol, options["timeframe"], start, end)
        self.stdout.write(self.style.SUCCESS(f"upserted {count} feature snapshots for {symbol.symbol}"))
