from django.core.management.base import BaseCommand

from apps.ml.evaluation import evaluate_model
from apps.ml.models import ModelVersion
from apps.ml.prediction import DEFAULT_WIN_PROBABILITY_THRESHOLD


class Command(BaseCommand):
    help = "Evaluate a ModelVersion on the test split: classification metrics + baseline vs. filtered trading comparison."

    def add_arguments(self, parser):
        parser.add_argument("--model-version-id", type=int, required=True)
        parser.add_argument("--threshold", type=float, default=DEFAULT_WIN_PROBABILITY_THRESHOLD)

    def handle(self, *args, **options):
        model_version = ModelVersion.objects.get(id=options["model_version_id"])
        results = evaluate_model(model_version, threshold=options["threshold"])

        test = results["test"]
        comparison = results["trading_comparison"]
        self.stdout.write(self.style.SUCCESS(
            f"test: accuracy {test['accuracy']:.3f}, precision {test['precision']:.3f}, "
            f"recall {test['recall']:.3f}, f1 {test['f1']:.3f}, roc_auc {test['roc_auc']}"
        ))
        self.stdout.write(
            f"baseline:  return {comparison['baseline']['total_return_pct']:.2f}%, "
            f"PF {comparison['baseline']['profit_factor']}, "
            f"max_dd {comparison['baseline']['max_drawdown_pct']:.2f}%, "
            f"sharpe {comparison['baseline']['sharpe_ratio']}, "
            f"trades {comparison['baseline']['total_trades']}"
        )
        self.stdout.write(
            f"filtered:  return {comparison['filtered']['total_return_pct']:.2f}%, "
            f"PF {comparison['filtered']['profit_factor']}, "
            f"max_dd {comparison['filtered']['max_drawdown_pct']:.2f}%, "
            f"sharpe {comparison['filtered']['sharpe_ratio']}, "
            f"trades {comparison['filtered']['total_trades']} "
            f"(threshold >= {options['threshold']})"
        )
