from datetime import date, timedelta

import pytest

from app.domain.models import Bar, Signal
from app.domain.strategy import FibonacciRetracementStrategy


def make_bars(closes):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c + 0.5, low=c - 0.5, close=c)
        for i, c in enumerate(closes)
    ]


class TestFibonacciRetracementStrategy:
    def test_rejects_invalid_levels(self):
        with pytest.raises(ValueError):
            FibonacciRetracementStrategy(entry_level=0.2, exit_level=0.6)  # exit > entry
        with pytest.raises(ValueError):
            FibonacciRetracementStrategy(entry_level=1.2, exit_level=0.2)
        with pytest.raises(ValueError):
            FibonacciRetracementStrategy(lookback=1)

    def test_signal_count_matches_bar_count(self):
        strategy = FibonacciRetracementStrategy(lookback=5)
        bars = make_bars([100, 102, 104, 103, 105, 107, 106, 108])
        signals = strategy.generate_signals(bars)
        assert len(signals) == len(bars)

    def test_warmup_period_is_all_hold(self):
        strategy = FibonacciRetracementStrategy(lookback=5)
        bars = make_bars([100, 101, 102])  # fewer bars than lookback
        signals = strategy.generate_signals(bars)
        assert all(s == Signal.HOLD for s in signals)

    def test_buys_on_bounce_and_sells_on_recovery(self):
        # Rally to 120, pull back to 100 (near the 61.8% retracement of a
        # 100->120 swing is ~107.6), then recover back up past 120.
        strategy = FibonacciRetracementStrategy(lookback=10, entry_level=0.618, exit_level=0.236)
        closes = [100, 105, 110, 115, 120, 115, 110, 105, 100, 108, 112, 116, 120, 121, 122]
        bars = make_bars(closes)

        signals = strategy.generate_signals(bars)

        assert Signal.BUY in signals
        assert Signal.SELL in signals
        # Should never hold two BUYs in a row without a SELL between them.
        holding = False
        for s in signals:
            if s == Signal.BUY:
                assert not holding, "opened a second position while already holding"
                holding = True
            elif s == Signal.SELL:
                assert holding, "sold without an open position"
                holding = False

    def test_never_signals_when_truly_flat(self):
        # high == low == close for every bar -> zero volatility, zero span.
        strategy = FibonacciRetracementStrategy(lookback=5)
        start = date(2024, 1, 1)
        bars = [
            Bar(date=start + timedelta(days=i), open=100, high=100, low=100, close=100)
            for i in range(15)
        ]
        signals = strategy.generate_signals(bars)
        assert all(s == Signal.HOLD for s in signals)
