from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand

from apps.agents.comparison import compare_strategies
from apps.market.services import resolve_market_symbol
from apps.strategy.models import StrategyConfig

LABELS = {
    "A_baseline": "A. Baseline strategy",
    "B_quant_xgboost": "B. Quant + XGBoost",
    "C_quant_ai_reviewer": "C. Quant + single AI reviewer",
    "D_quant_trading_agents": "D. Quant + TradingAgents",
}


class Command(BaseCommand):
    help = (
        "Compare baseline / quant+XGBoost / quant+AI-reviewer / quant+TradingAgents "
        "over the same range. C and D make real AI calls per qualifying historical "
        "candidate (cached where possible) -- keep the range small unless you mean to spend."
    )

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

        results = compare_strategies(strategy_config, symbol, options["timeframe"], start, end)

        for key, label in LABELS.items():
            m = results[key]
            self.stdout.write(self.style.SUCCESS(
                f"{label}: return {m['total_return_pct']:.2f}%, PF {m['profit_factor']}, "
                f"max_dd {m['max_drawdown_pct']:.2f}%, sharpe {m['sharpe_ratio']}, "
                f"trades {m['total_trades']}, AI calls {m['ai_calls']}, "
                f"AI tokens {m['ai_tokens']}, est. AI cost ${m['estimated_ai_cost']:.4f}"
            ))
