from django.core.management.base import BaseCommand

from apps.market.services import resolve_market_symbol, update_recent


class Command(BaseCommand):
    help = "Incrementally fetch the latest candles for a symbol/timeframe."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")

    def handle(self, *args, **options):
        symbol = resolve_market_symbol(options["symbol"])
        count = update_recent(symbol, options["timeframe"])
        self.stdout.write(self.style.SUCCESS(f"updated {count} candles for {symbol.symbol}"))
