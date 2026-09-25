from django import forms

from apps.market.models import MarketSymbol
from apps.strategy.models import StrategyConfig

TIMEFRAME_CHOICES = [("15m", "15m"), ("1h", "1h"), ("4h", "4h"), ("1d", "1d")]
POSITION_SIZE_CHOICES = [("percentage_of_equity", "Percentage of equity"), ("fixed_cash", "Fixed cash")]


class BacktestRunForm(forms.Form):
    strategy = forms.ModelChoiceField(queryset=StrategyConfig.objects.all())
    symbol = forms.ModelChoiceField(queryset=MarketSymbol.objects.all())
    timeframe = forms.ChoiceField(choices=TIMEFRAME_CHOICES, initial="1h")
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    initial_capital = forms.FloatField(initial=10000, min_value=0)
    fee = forms.FloatField(initial=0.0004, min_value=0, label="Fee (fraction, e.g. 0.0004 = 0.04%)")
    slippage_percent = forms.FloatField(initial=0.0005, min_value=0)
    position_size_type = forms.ChoiceField(choices=POSITION_SIZE_CHOICES, initial="percentage_of_equity")
    risk_per_trade = forms.FloatField(
        initial=0.01, min_value=0, label="Risk per trade (fraction of equity, or cash amount if fixed)"
    )

    def engine_overrides(self) -> dict:
        data = self.cleaned_data
        return {
            "position_size_type": data["position_size_type"],
            "risk_per_trade": data["risk_per_trade"],
            "taker_fee": data["fee"],
            "slippage_percent": data["slippage_percent"],
        }
