from django.core.management.base import BaseCommand

from apps.market.services import resolve_market_symbol
from apps.ml.training import train_model
from apps.strategy.models import StrategyConfig


class Command(BaseCommand):
    help = "Train an XGBoost win-probability model from the datasets build_ml_dataset wrote."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", required=True, help="e.g. ema_rsi")
        parser.add_argument("--symbol", required=True, help="e.g. BTCUSDT")
        parser.add_argument("--timeframe", required=True, help="e.g. 1h")
        parser.add_argument("--name", default=None, help="Model name (default: <strategy>_xgboost)")

    def handle(self, *args, **options):
        strategy_config, _ = StrategyConfig.objects.get_or_create(
            name=options["strategy"], defaults={"timeframe": options["timeframe"]}
        )
        symbol = resolve_market_symbol(options["symbol"])
        name = options["name"] or f"{options['strategy']}_xgboost"

        model_version = train_model(strategy_config, symbol, options["timeframe"], name)
        m = model_version.validation_metrics["validation"]
        self.stdout.write(self.style.SUCCESS(
            f"ModelVersion #{model_version.id} '{model_version.name}': "
            f"val accuracy {m['accuracy']:.3f}, precision {m['precision']:.3f}, recall {m['recall']:.3f}, "
            f"f1 {m['f1']:.3f}, roc_auc {m['roc_auc']}"
        ))
