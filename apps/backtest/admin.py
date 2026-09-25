from django.contrib import admin

from .models import BacktestRun, BacktestTrade


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = ("id", "strategy", "symbol", "timeframe", "status", "initial_capital", "final_capital")
    list_filter = ("strategy", "symbol", "timeframe", "status")


@admin.register(BacktestTrade)
class BacktestTradeAdmin(admin.ModelAdmin):
    list_display = ("backtest", "side", "entry_timestamp", "exit_timestamp", "exit_reason", "net_pnl")
    list_filter = ("backtest", "side", "exit_reason")
