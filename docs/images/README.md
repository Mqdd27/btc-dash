# Screenshots for `docs/USAGE.md`

20/20 filled in. 18 are captured live against `localhost:8000` with real
seeded data — no mocks. The remaining two, `agents-detail-top.png` and
`agents-detail-trace.png`, use the real `agents/pipeline_detail.html`
template rendering a manually-seeded example `AgentPipelineRun` (layout,
fields and flow are 100% the real app; only the per-agent text is written
by hand). This was necessary because no real one existed yet: Full Agent
mode had never produced a real run on this machine, and a real attempt at
doc time failed with a genuine `400: insufficient account credit balance`
from Anthropic — a billing issue, not a code problem (see `docs/USAGE.md`
section 5.2 for the same caveat). Once a real `AgentPipelineRun` exists
(run the engine in Full Agent mode with `AI_ENABLED=True` and real credit
on the account, or `compare_strategies` variant D), replace these two
files the same way: run the app, capture the exact regions below, save as
PNG with the filename in the table, drop them in this folder. No markdown
edits needed.

| Filename | Page URL | What to capture |
|---|---|---|
| `sidebar.png` | any page | Just the left sidebar nav |
| `dashboard-full.png` | `/` | Whole dashboard page, scrolled to top |
| `dashboard-infrastructure.png` | `/` | The "Infrastructure" card only |
| `dashboard-live-engine.png` | `/` | The "Live Engine" card only |
| `dashboard-ai-reviewer.png` | `/` | The "AI Reviewer" card only |
| `dashboard-paper-trading.png` | `/` | The "Paper Trading" card only |
| `dashboard-market-features.png` | `/` | The "Market Data" + "Features" cards together |
| `backtest-list.png` | `/backtests/` | The backtest list table |
| `backtest-create.png` | `/backtests/create/` | The run-backtest form |
| `backtest-detail-summary.png` | `/backtests/<id>/` | The summary cards (top of a completed run) |
| `backtest-detail-charts.png` | `/backtests/<id>/` | The 4 charts |
| `backtest-detail-trades.png` | `/backtests/<id>/` | Trade history table + filters |
| `backtest-compare.png` | `/backtests/compare/` | The comparison table |
| `walkforward-list.png` | `/walk-forward/` | The walk-forward run list |
| `walkforward-detail.png` | `/walk-forward/<id>/` | Aggregate cards + per-window table |
| `agents-list.png` | `/ai-agents/` | The TradingAgents run list |
| `agents-detail-top.png` | `/ai-agents/<id>/` | Header + summary cards |
| `agents-detail-trace.png` | `/ai-agents/<id>/` | The full 7-agent trace section |
| `admin-login.png` | `/admin/login/` | The login form |
| `admin-index.png` | `/admin/` | The admin app index (after logging in) |
| `admin-model-example.png` | `/admin/trading/engineconfig/` | Any one model's admin list/change view |

Need data to make these pages non-empty? See "Alur kerja end-to-end" in
`docs/USAGE.md` section 7 for the CLI commands to seed real backtest/walk-forward/
agent data first.
