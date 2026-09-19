from datetime import date, timedelta

import pytest

from app.domain.indicators import (
    SwingRange,
    fibonacci_retracement_levels,
    find_swing_range,
    rolling_support_resistance,
    standard_pivot_points,
)
from app.domain.models import Bar


def make_bars(highs, lows, closes):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=h, low=l, close=c)
        for i, (h, l, c) in enumerate(zip(highs, lows, closes))
    ]


class TestSwingRange:
    def test_rejects_high_below_low(self):
        with pytest.raises(ValueError):
            SwingRange(swing_high=10, swing_low=20)

    def test_find_swing_range_picks_extremes_in_window(self):
        bars = make_bars(highs=[10, 15, 12, 20, 11], lows=[8, 9, 10, 14, 9], closes=[9, 12, 11, 18, 10])
        swing = find_swing_range(bars, lookback=5)
        assert swing.swing_high == 20
        assert swing.swing_low == 8

    def test_find_swing_range_respects_lookback_window(self):
        bars = make_bars(highs=[100, 10, 10], lows=[90, 5, 5], closes=[95, 8, 8])
        # lookback=2 should ignore the first bar (high=100) entirely.
        swing = find_swing_range(bars, lookback=2)
        assert swing.swing_high == 10
        assert swing.swing_low == 5

    def test_empty_bars_raises(self):
        with pytest.raises(ValueError):
            find_swing_range([], lookback=5)


class TestFibonacciRetracementLevels:
    def test_uptrend_levels_descend_from_high(self):
        swing = SwingRange(swing_high=200, swing_low=100)
        levels = fibonacci_retracement_levels(swing, uptrend=True)
        assert levels[0.0] == 200
        assert levels[1.0] == 100
        assert levels[0.5] == 150
        assert levels[0.618] == pytest.approx(200 - 100 * 0.618)

    def test_downtrend_levels_ascend_from_low(self):
        swing = SwingRange(swing_high=200, swing_low=100)
        levels = fibonacci_retracement_levels(swing, uptrend=False)
        assert levels[0.0] == 100
        assert levels[1.0] == 200
        assert levels[0.618] == pytest.approx(100 + 100 * 0.618)

    def test_zero_span_gives_flat_levels(self):
        swing = SwingRange(swing_high=150, swing_low=150)
        levels = fibonacci_retracement_levels(swing, uptrend=True)
        assert all(price == 150 for price in levels.values())


class TestStandardPivotPoints:
    def test_pivot_point_formula(self):
        bar = Bar(date=date(2024, 1, 1), open=100, high=110, low=90, close=105)
        pivots = standard_pivot_points(bar)
        expected_pivot = (110 + 90 + 105) / 3
        assert pivots.pivot == pytest.approx(expected_pivot)
        assert pivots.r1 == pytest.approx(2 * expected_pivot - 90)
        assert pivots.s1 == pytest.approx(2 * expected_pivot - 110)
        # Resistance levels should be ordered r1 < r2 < r3
        assert pivots.r1 < pivots.r2 < pivots.r3
        # Support levels should be ordered s1 > s2 > s3
        assert pivots.s1 > pivots.s2 > pivots.s3


class TestRollingSupportResistance:
    def test_output_length_matches_input(self):
        bars = make_bars(highs=[10, 12, 11, 15, 13], lows=[8, 9, 9, 10, 11], closes=[9, 11, 10, 13, 12])
        result = rolling_support_resistance(bars, window=3)
        assert len(result) == len(bars)

    def test_early_bars_use_partial_window(self):
        bars = make_bars(highs=[10, 20], lows=[5, 15], closes=[7, 18])
        result = rolling_support_resistance(bars, window=5)
        # First bar has no history before it, so window is just itself.
        assert result[0] == {"support": 5, "resistance": 10}
        # Second bar's window (with window=5) covers both bars.
        assert result[1] == {"support": 5, "resistance": 20}

    def test_rejects_non_positive_window(self):
        bars = make_bars(highs=[10], lows=[5], closes=[7])
        with pytest.raises(ValueError):
            rolling_support_resistance(bars, window=0)
