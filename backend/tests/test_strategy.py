from datetime import date, timedelta

import pytest

from app.domain.models import Bar, Signal
from app.domain.strategy import SmaCrossoverStrategy


def make_bars(closes):
    """Helper: build a list of Bar objects from a list of close prices,
    one bar per day starting 2024-01-01. open=high=low=close for simplicity."""
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c, low=c, close=c)
        for i, c in enumerate(closes)
    ]


class TestSmaCrossoverStrategy:
    def test_rejects_invalid_periods(self):
        with pytest.raises(ValueError):
            SmaCrossoverStrategy(fast_period=20, slow_period=5)
        with pytest.raises(ValueError):
            SmaCrossoverStrategy(fast_period=0, slow_period=5)

    def test_all_hold_during_warmup(self):
        strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)
        bars = make_bars([10, 10, 10])  # fewer bars than slow_period
        signals = strategy.generate_signals(bars)
        assert signals == [Signal.HOLD, Signal.HOLD, Signal.HOLD]

    def test_signal_count_matches_bar_count(self):
        strategy = SmaCrossoverStrategy(fast_period=3, slow_period=5)
        bars = make_bars([10, 11, 12, 13, 12, 11, 10, 9, 10, 12, 14])
        signals = strategy.generate_signals(bars)
        assert len(signals) == len(bars)

    def test_detects_upward_crossover(self):
        # Prices fall then rise sharply: fast SMA should cross above slow SMA.
        strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)
        closes = [10, 9, 8, 7, 12, 14, 16, 18]
        bars = make_bars(closes)
        signals = strategy.generate_signals(bars)
        assert Signal.BUY in signals

    def test_detects_downward_crossover(self):
        # Prices rise then fall sharply: fast SMA should cross below slow SMA.
        strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)
        closes = [7, 8, 9, 10, 5, 3, 1, 0]
        bars = make_bars(closes)
        signals = strategy.generate_signals(bars)
        assert Signal.SELL in signals

    def test_flat_prices_never_signal(self):
        strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)
        bars = make_bars([10] * 10)
        signals = strategy.generate_signals(bars)
        assert all(s == Signal.HOLD for s in signals)
