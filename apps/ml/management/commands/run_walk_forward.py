from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand

from apps.market.services import resolve_market_symbol
from apps.ml.prediction import DEFAULT_WIN_PROBABILITY_THRESHOLD
from apps.ml.walk_forward import run_walk_forward
from apps.strategy.models import StrategyConfig


class Command(BaseCommand):
    help = "Run walk-forward validation: retrain and out-of-sample-test the model across sliding/expanding windows."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", required=True, help="e.g. ema_rsi")
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")
        parser.add_argument("--start", required=True, help="YYYY-MM-DD")
        parser.add_argument("--end", required=True, help="YYYY-MM-DD")
        parser.add_argument("--mode", choices=["rolling", "expanding"], default="rolling")
        parser.add_argument("--training-months", type=int, default=24)
        parser.add_argument("--test-months", type=int, default=3)
        parser.add_argument("--retrain-months", type=int, default=3)
        parser.add_argument("--threshold", type=float, default=DEFAULT_WIN_PROBABILITY_THRESHOLD)

    def handle(self, *args, **options):
        start = datetime.strptime(options["start"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
        end = datetime.strptime(options["end"], "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)

        strategy_config, _ = StrategyConfig.objects.get_or_create(
            name=options["strategy"], defaults={"timeframe": options["timeframe"]}
        )
        symbol = resolve_market_symbol(options["symbol"])

        run = run_walk_forward(
            strategy_config, symbol, options["timeframe"], start, end, options["mode"],
            training_months=options["training_months"], test_months=options["test_months"],
            retrain_months=options["retrain_months"], threshold=options["threshold"],
        )

        windows = run.windows.all()
        self.stdout.write(self.style.SUCCESS(f"WalkForwardRun #{run.id}: {windows.count()} windows"))
        for w in windows:
            m = w.metrics
            self.stdout.write(
                f"  window {w.index}: train {w.train_start:%Y-%m-%d}..{w.train_end:%Y-%m-%d}, "
                f"test {w.test_start:%Y-%m-%d}..{w.test_end:%Y-%m-%d}, "
                f"trades {m['total_trades']}, return {m['total_return_pct']:.2f}%"
            )
        agg = run.aggregate_metrics
        self.stdout.write(self.style.SUCCESS(
            f"aggregate (test windows only): {agg['total_trades']} trades, "
            f"return {agg['total_return_pct']:.2f}%, PF {agg['profit_factor']}, "
            f"max_dd {agg['max_drawdown_pct']:.2f}%, sharpe {agg['sharpe_ratio']}"
        ))
