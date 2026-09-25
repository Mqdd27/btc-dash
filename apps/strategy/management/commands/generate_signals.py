from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand

from apps.market.services import resolve_market_symbol
from apps.strategy.models import StrategyConfig
from apps.strategy.services import generate_signals


class Command(BaseCommand):
    help = "Run a strategy over stored features and store LONG/SHORT SignalCandidates."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", required=True, help="e.g. ema_rsi")
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")
        parser.add_argument("--start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--end", required=True, help="YYYY-MM-DD")

    def handle(self, *args, **options):
        start = datetime.strptime(options["start"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
        end = datetime.strptime(options["end"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)

        strategy_config, _ = StrategyConfig.objects.get_or_create(
            name=options["strategy"], defaults={"timeframe": options["timeframe"]}
        )
        symbol = resolve_market_symbol(options["symbol"])
        count = generate_signals(strategy_config, symbol, options["timeframe"], start, end)
        self.stdout.write(self.style.SUCCESS(f"generated {count} signal candidates"))
