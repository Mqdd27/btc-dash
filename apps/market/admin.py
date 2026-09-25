from django.contrib import admin

from .models import Candle, FundingRate, MarketSymbol, OpenInterest


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
