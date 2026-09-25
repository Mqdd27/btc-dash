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
