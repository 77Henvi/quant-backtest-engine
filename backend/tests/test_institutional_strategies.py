from datetime import date, timedelta
import pytest

from app.domain.models import Bar, Signal
from app.domain.strategy import (
    BollingerMeanReversionStrategy,
    DualMomentumStrategy,
    MACDCrossoverStrategy,
)


def make_bars(closes):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c * 1.02, low=c * 0.98, close=c)
        for i, c in enumerate(closes)
    ]


class TestInstitutionalStrategies:
    def test_macd_strategy_validation(self):
        with pytest.raises(ValueError):
            MACDCrossoverStrategy(fast_period=26, slow_period=12)
        with pytest.raises(ValueError):
            MACDCrossoverStrategy(fast_period=-5, slow_period=20)

    def test_macd_strategy_signals(self):
        # 30 falling bars then 30 rising bars to trigger MACD bullish crossover
        prices = [100 - i * 1.5 for i in range(30)] + [55 + i * 2.5 for i in range(35)]
        bars = make_bars(prices)
        strat = MACDCrossoverStrategy(fast_period=5, slow_period=15, signal_period=5)
        signals = strat.generate_signals(bars)
        assert len(signals) == len(bars)
        assert Signal.BUY in signals

    def test_bollinger_strategy_validation(self):
        with pytest.raises(ValueError):
            BollingerMeanReversionStrategy(period=0)
        with pytest.raises(ValueError):
            BollingerMeanReversionStrategy(num_std=-1.0)

    def test_bollinger_strategy_execution(self):
        prices = [100.0] * 25 + [80.0, 82.0, 95.0, 105.0]
        bars = make_bars(prices)
        strat = BollingerMeanReversionStrategy(period=10, num_std=1.5)
        signals = strat.generate_signals(bars)
        assert len(signals) == len(bars)

    def test_dual_momentum_strategy(self):
        prices = [100.0 + i for i in range(50)] + [140.0 - i * 2 for i in range(10)] + [130.0 + i * 2 for i in range(15)]
        bars = make_bars(prices)
        strat = DualMomentumStrategy(ema_period=20, rsi_period=10, rsi_entry=35, rsi_exit=65)
        signals = strat.generate_signals(bars)
        assert len(signals) == len(bars)
