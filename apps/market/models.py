from django.db import models


class MarketSymbol(models.Model):
    symbol = models.CharField(max_length=20, unique=True)  # e.g. "BTCUSDT"
    base_asset = models.CharField(max_length=10)
    quote_asset = models.CharField(max_length=10)
    exchange = models.CharField(max_length=20, default="binance")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.symbol


class Candle(models.Model):
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="candles")
    timeframe = models.CharField(max_length=10)  # ccxt-style: "1h", "15m", "4h", ...
    timestamp = models.DateTimeField()  # candle open time, UTC

    open = models.DecimalField(max_digits=20, decimal_places=8)
    high = models.DecimalField(max_digits=20, decimal_places=8)
    low = models.DecimalField(max_digits=20, decimal_places=8)
    close = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=24, decimal_places=8)
    quote_volume = models.DecimalField(max_digits=28, decimal_places=8, null=True, blank=True)
    trades_count = models.PositiveIntegerField(null=True, blank=True)

    # False while the candle's period hasn't closed yet (still forming).
    closed = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "timeframe", "timestamp"], name="unique_candle"
            )
        ]
        indexes = [models.Index(fields=["symbol", "timeframe", "timestamp"])]
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.symbol_id} {self.timeframe} {self.timestamp}"


class FundingRate(models.Model):
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="funding_rates")
    timestamp = models.DateTimeField()
    funding_rate = models.DecimalField(max_digits=12, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["symbol", "timestamp"], name="unique_funding_rate")
        ]
        ordering = ["timestamp"]


class OpenInterest(models.Model):
    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="open_interests")
    timestamp = models.DateTimeField()
    open_interest = models.DecimalField(max_digits=24, decimal_places=8)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["symbol", "timestamp"], name="unique_open_interest")
        ]
        ordering = ["timestamp"]


class FeatureSnapshot(models.Model):
    """One row of engineered features per finalized candle. All values are computed
    using only that candle's timestamp and earlier -- see apps/market/features.py."""

    symbol = models.ForeignKey(MarketSymbol, on_delete=models.CASCADE, related_name="feature_snapshots")
    timeframe = models.CharField(max_length=10)
    timestamp = models.DateTimeField()

    # technical
    return_1 = models.FloatField(null=True)
    return_4 = models.FloatField(null=True)
    return_24 = models.FloatField(null=True)
    log_return = models.FloatField(null=True)
    ema_10 = models.FloatField(null=True)
    ema_20 = models.FloatField(null=True)
    ema_50 = models.FloatField(null=True)
    ema_100 = models.FloatField(null=True)
    ema_200 = models.FloatField(null=True)
    rsi_14 = models.FloatField(null=True)
    macd = models.FloatField(null=True)
    macd_signal = models.FloatField(null=True)
    macd_histogram = models.FloatField(null=True)
    atr_14 = models.FloatField(null=True)
    bollinger_upper = models.FloatField(null=True)
    bollinger_middle = models.FloatField(null=True)
    bollinger_lower = models.FloatField(null=True)
    bollinger_bandwidth = models.FloatField(null=True)
    rolling_volatility = models.FloatField(null=True)
    volume_sma = models.FloatField(null=True)
    volume_change = models.FloatField(null=True)
    volume_zscore = models.FloatField(null=True)

    # derived
    distance_close_ema20 = models.FloatField(null=True)
    distance_close_ema50 = models.FloatField(null=True)
    distance_close_ema200 = models.FloatField(null=True)
    ema20_vs_ema50 = models.FloatField(null=True)
    ema50_vs_ema200 = models.FloatField(null=True)
    atr_percent = models.FloatField(null=True)
    candle_body_percent = models.FloatField(null=True)
    upper_wick_percent = models.FloatField(null=True)
    lower_wick_percent = models.FloatField(null=True)

    # derivatives (only populated where funding/OI data exists)
    funding_rate = models.FloatField(null=True)
    funding_rate_change = models.FloatField(null=True)
    open_interest = models.FloatField(null=True)
    open_interest_change = models.FloatField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "timeframe", "timestamp"], name="unique_feature_snapshot"
            )
        ]
        ordering = ["timestamp"]
