from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand

from apps.backtest.services import run_backtest
from apps.market.services import resolve_market_symbol
from apps.strategy.models import StrategyConfig


class Command(BaseCommand):
    help = "Run a deterministic backtest for a strategy over a date range."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", required=True, help="e.g. ema_rsi")
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")
        parser.add_argument("--start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--end", required=True, help="YYYY-MM-DD")
        parser.add_argument("--initial-capital", type=float, default=10000)

    def handle(self, *args, **options):
        start = datetime.strptime(options["start"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
        end = datetime.strptime(options["end"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)

        strategy_config, _ = StrategyConfig.objects.get_or_create(
            name=options["strategy"], defaults={"timeframe": options["timeframe"]}
        )
        symbol = resolve_market_symbol(options["symbol"])

        backtest = run_backtest(
            strategy_config, symbol, options["timeframe"], start, end, options["initial_capital"]
        )

        m = backtest.metrics
        self.stdout.write(self.style.SUCCESS(
            f"backtest #{backtest.id}: {m['total_trades']} trades, "
            f"final capital {m['final_capital']:.2f} ({m['total_return_pct']:.2f}%), "
            f"win rate {m['win_rate_pct']:.1f}%, max drawdown {m['max_drawdown_pct']:.2f}%, "
            f"buy&hold {m['benchmark']['total_return_pct']:.2f}%"
        ))
