from datetime import date, timedelta

import pytest

from app.domain.models import Bar, Signal
from app.domain.strategy import RSIMeanReversionStrategy


def make_bars(closes):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c + 0.5, low=c - 0.5, close=c)
        for i, c in enumerate(closes)
    ]


class TestRSIMeanReversionStrategy:
    def test_rejects_invalid_thresholds(self):
        with pytest.raises(ValueError):
            RSIMeanReversionStrategy(oversold=70, overbought=30)  # swapped
        with pytest.raises(ValueError):
            RSIMeanReversionStrategy(deep_oversold=40, oversold=30)  # deep must be lowest

    def test_signal_count_matches_bar_count(self):
        strategy = RSIMeanReversionStrategy(period=14)
        closes = [10, 12, 9, 15, 11, 8, 20, 5, 18, 13, 9, 22, 7, 16, 10, 14, 19, 6, 21, 12]
        bars = make_bars(closes)
        signals = strategy.generate_signals(bars)
        assert len(signals) == len(bars)

    def test_warmup_period_is_all_hold(self):
        strategy = RSIMeanReversionStrategy(period=14)
        bars = make_bars([10, 11, 12, 13, 14])  # far fewer bars than period
        signals = strategy.generate_signals(bars)
        assert all(s == Signal.HOLD for s in signals)

    def test_never_signals_on_flat_prices(self):
        strategy = RSIMeanReversionStrategy(period=14)
        bars = make_bars([100] * 30)
        signals = strategy.generate_signals(bars)
        assert all(s == Signal.HOLD for s in signals)

    def test_deep_selloff_then_recovery_triggers_buy(self):
        # Sharp drop (drives RSI into oversold territory) followed by a
        # recovery back up should trigger a BUY on the way back up.
        closes = (
            list(range(100, 130))  # calm warm-up so RSI has history
            + [x for x in range(130, 90, -4)]  # sharp selloff -> oversold
            + list(range(90, 140, 3))  # recovery -> should cross back up
        )
        bars = make_bars(closes)
        strategy = RSIMeanReversionStrategy(period=14)
        signals = strategy.generate_signals(bars)
        assert Signal.BUY in signals

    def test_never_holds_two_positions_without_a_sell_between(self):
        closes = (
            list(range(100, 130))
            + [x for x in range(130, 60, -3)]  # deep selloff, multiple oversold dips
            + [x for x in range(60, 150, 2)]  # long recovery through overbought
            + [x for x in range(150, 60, -3)]  # another selloff
            + [x for x in range(60, 150, 2)]  # another recovery
        )
        bars = make_bars(closes)
        strategy = RSIMeanReversionStrategy(period=14)
        signals = strategy.generate_signals(bars)

        holding = False
        for s in signals:
            if s == Signal.BUY:
                assert not holding, "opened a second position while already holding"
                holding = True
            elif s == Signal.SELL:
                assert holding, "sold without an open position"
                holding = False
