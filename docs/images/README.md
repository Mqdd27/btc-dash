# Screenshots needed for `docs/USAGE.md`

Take these with the app running (`./scripts/start_dev.sh`), save as PNG with
the exact filename below, drop them in this folder. `docs/USAGE.md` already
references every one of these paths — no markdown edits needed once they exist.

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
