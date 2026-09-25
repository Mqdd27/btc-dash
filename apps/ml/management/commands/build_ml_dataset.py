from django.core.management.base import BaseCommand

from apps.market.services import resolve_market_symbol
from apps.ml.dataset import build_ml_dataset
from apps.strategy.models import StrategyConfig


class Command(BaseCommand):
    help = "Build train/validation/test CSV datasets from historical backtest outcomes."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", required=True, help="e.g. ema_rsi")
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")

    def handle(self, *args, **options):
        strategy_config, _ = StrategyConfig.objects.get_or_create(
            name=options["strategy"], defaults={"timeframe": options["timeframe"]}
        )
        symbol = resolve_market_symbol(options["symbol"])

        paths = build_ml_dataset(strategy_config, symbol, options["timeframe"])
        for split, path in paths.items():
            self.stdout.write(self.style.SUCCESS(f"{split}: {path}"))
