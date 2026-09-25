from django.contrib import admin

from .models import Candle, FeatureSnapshot, FundingRate, MarketSymbol, OpenInterest


@admin.register(MarketSymbol)
class MarketSymbolAdmin(admin.ModelAdmin):
    list_display = ("symbol", "base_asset", "quote_asset", "exchange", "active", "created_at")


@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timeframe", "timestamp", "close", "closed")
    list_filter = ("symbol", "timeframe", "closed")


@admin.register(FundingRate)
class FundingRateAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timestamp", "funding_rate")


@admin.register(OpenInterest)
class OpenInterestAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timestamp", "open_interest")


@admin.register(FeatureSnapshot)
class FeatureSnapshotAdmin(admin.ModelAdmin):
    list_display = ("symbol", "timeframe", "timestamp", "rsi_14", "macd")
    list_filter = ("symbol", "timeframe")
