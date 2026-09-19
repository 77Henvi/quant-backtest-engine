from datetime import date, timedelta

import pytest

from app.domain.indicators import (
    bollinger_bands,
    exponential_moving_average,
    macd,
    relative_strength_index,
    simple_moving_average,
)
from app.domain.models import Bar


def make_bars(closes):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c + 0.5, low=c - 0.5, close=c)
        for i, c in enumerate(closes)
    ]


class TestSimpleMovingAverage:
    def test_rejects_non_positive_period(self):
        with pytest.raises(ValueError):
            simple_moving_average([1, 2, 3], period=0)

    def test_none_during_warmup_then_correct_average(self):
        result = simple_moving_average([1, 2, 3, 4, 5], period=3)
        assert result[:2] == [None, None]
        assert result[2] == pytest.approx(2.0)  # mean(1,2,3)
        assert result[4] == pytest.approx(4.0)  # mean(3,4,5)


class TestExponentialMovingAverage:
    def test_rejects_non_positive_period(self):
        with pytest.raises(ValueError):
            exponential_moving_average([1, 2, 3], period=0)

    def test_seeds_with_sma_then_smooths(self):
        values = [1, 2, 3, 4, 5, 6]
        result = exponential_moving_average(values, period=3)
        assert result[:2] == [None, None]
        assert result[2] == pytest.approx(2.0)  # seeded as SMA(1,2,3)
        # EMA should track upward with the rising input series.
        assert result[3] > result[2]
        assert result[5] > result[3]

    def test_too_few_values_returns_all_none(self):
        result = exponential_moving_average([1, 2], period=5)
        assert result == [None, None]


class TestRelativeStrengthIndex:
    def test_rejects_non_positive_period(self):
        bars = make_bars([10, 11, 12])
        with pytest.raises(ValueError):
            relative_strength_index(bars, period=0)

    def test_warmup_period_is_none(self):
        bars = make_bars([10, 11, 12, 13, 14])
        result = relative_strength_index(bars, period=14)
        assert all(v is None for v in result)  # not enough bars yet

    def test_only_gains_scores_100(self):
        # Monotonically increasing closes: zero losses -> RSI pinned at 100.
        closes = list(range(10, 10 + 20))
        bars = make_bars(closes)
        result = relative_strength_index(bars, period=14)
        assert result[14] == pytest.approx(100.0)

    def test_only_losses_scores_0(self):
        closes = list(range(30, 30 - 20, -1))
        bars = make_bars(closes)
        result = relative_strength_index(bars, period=14)
        assert result[14] == pytest.approx(0.0)

    def test_flat_prices_scores_50(self):
        bars = make_bars([100] * 20)
        result = relative_strength_index(bars, period=14)
        assert result[14] == pytest.approx(50.0)

    def test_result_always_between_0_and_100(self):
        closes = [10, 12, 9, 15, 11, 8, 20, 5, 18, 13, 9, 22, 7, 16, 10, 14, 19, 6, 21, 12]
        bars = make_bars(closes)
        result = relative_strength_index(bars, period=14)
        for value in result:
            if value is not None:
                assert 0.0 <= value <= 100.0


class TestMacd:
    def test_rejects_fast_period_not_less_than_slow(self):
        bars = make_bars([10, 11, 12])
        with pytest.raises(ValueError):
            macd(bars, fast_period=26, slow_period=12)

    def test_warmup_period_has_none_fields(self):
        bars = make_bars(list(range(10, 30)))
        result = macd(bars, fast_period=5, slow_period=10, signal_period=3)
        assert result[0].macd_line is None
        assert result[0].signal_line is None
        assert result[0].histogram is None

    def test_eventually_produces_real_values(self):
        bars = make_bars(list(range(10, 60)))
        result = macd(bars, fast_period=5, slow_period=10, signal_period=3)
        last = result[-1]
        assert last.macd_line is not None
        assert last.signal_line is not None
        assert last.histogram == pytest.approx(last.macd_line - last.signal_line)

    def test_uptrend_gives_positive_macd_line(self):
        # Fast EMA reacts quicker than slow EMA in a steady uptrend, so
        # it should sit above the slow EMA -> positive MACD line.
        bars = make_bars(list(range(10, 60)))
        result = macd(bars, fast_period=5, slow_period=10, signal_period=3)
        assert result[-1].macd_line > 0


class TestBollingerBands:
    def test_rejects_non_positive_period(self):
        bars = make_bars([10, 11, 12])
        with pytest.raises(ValueError):
            bollinger_bands(bars, period=0)

    def test_rejects_non_positive_num_std(self):
        bars = make_bars([10, 11, 12])
        with pytest.raises(ValueError):
            bollinger_bands(bars, period=2, num_std=0)

    def test_warmup_period_is_none(self):
        bars = make_bars([10, 11, 12])
        result = bollinger_bands(bars, period=20)
        assert all(b.middle is None and b.upper is None and b.lower is None for b in result)

    def test_upper_is_above_middle_is_above_lower(self):
        closes = [10, 12, 9, 15, 11, 8, 20, 5, 18, 13]
        bars = make_bars(closes)
        result = bollinger_bands(bars, period=5, num_std=2.0)
        for band in result:
            if band.middle is not None:
                assert band.upper > band.middle > band.lower

    def test_flat_prices_collapse_bands_to_the_middle(self):
        bars = make_bars([100] * 10)
        result = bollinger_bands(bars, period=5, num_std=2.0)
        last = result[-1]
        assert last.upper == pytest.approx(last.middle)
        assert last.lower == pytest.approx(last.middle)

    def test_wider_std_multiplier_widens_the_bands(self):
        closes = [10, 12, 9, 15, 11, 8, 20, 5, 18, 13]
        bars = make_bars(closes)
        narrow = bollinger_bands(bars, period=5, num_std=1.0)[-1]
        wide = bollinger_bands(bars, period=5, num_std=3.0)[-1]
        assert wide.upper > narrow.upper
        assert wide.lower < narrow.lower
