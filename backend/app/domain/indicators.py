"""
Technical analysis tools: Fibonacci retracement, pivot points, and
support/resistance levels.

These are published, public-domain formulas (the same math every
charting platform including TradingView implements) computed purely
from OHLC data already in our possession. No external API, no
copyrighted logic - just arithmetic, which is why this lives in the
domain layer alongside engine.py and metrics.py.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import Bar

# Standard Fibonacci retracement ratios used across all charting platforms.
FIBONACCI_RATIOS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


@dataclass(frozen=True)
class SwingRange:
    """The high/low used as the basis for a Fibonacci retracement."""

    swing_high: float
    swing_low: float

    def __post_init__(self) -> None:
        if self.swing_high < self.swing_low:
            raise ValueError("swing_high must be >= swing_low")


def find_swing_range(bars: List[Bar], lookback: int) -> SwingRange:
    """Find the highest high and lowest low over the last `lookback` bars."""
    if not bars:
        raise ValueError("bars must not be empty")
    if lookback <= 0:
        raise ValueError("lookback must be positive")

    window = bars[-lookback:]
    swing_high = max(b.high for b in window)
    swing_low = min(b.low for b in window)
    return SwingRange(swing_high=swing_high, swing_low=swing_low)


def fibonacci_retracement_levels(swing: SwingRange, uptrend: bool = True) -> Dict[float, float]:
    """
    Compute Fibonacci retracement price levels for a swing range.

    uptrend=True  -> retracement measured DOWN from the high (pullback in an uptrend)
    uptrend=False -> retracement measured UP from the low (pullback in a downtrend)

    Returns a dict mapping each ratio (0.0, 0.236, ... 1.0) to a price.
    """
    span = swing.swing_high - swing.swing_low
    levels: Dict[float, float] = {}
    for ratio in FIBONACCI_RATIOS:
        if uptrend:
            levels[ratio] = swing.swing_high - span * ratio
        else:
            levels[ratio] = swing.swing_low + span * ratio
    return levels


@dataclass(frozen=True)
class PivotPoints:
    """Standard (floor trader) pivot points for the NEXT period."""

    pivot: float
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


def standard_pivot_points(prior_bar: Bar) -> PivotPoints:
    """
    Classic floor-trader pivot points, computed from the prior period's
    high/low/close. Used to project intraday-style support/resistance
    for the next bar.
    """
    high, low, close = prior_bar.high, prior_bar.low, prior_bar.close
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    r3 = high + 2 * (pivot - low)
    s3 = low - 2 * (high - pivot)
    return PivotPoints(pivot=pivot, r1=r1, r2=r2, r3=r3, s1=s1, s2=s2, s3=s3)


def rolling_support_resistance(bars: List[Bar], window: int) -> List[Dict[str, float]]:
    """
    Simple rolling support/resistance: for each bar, the lowest low and
    highest high over the trailing `window` bars (inclusive). The first
    `window - 1` bars use whatever history is available.

    Returns one {"support": ..., "resistance": ...} dict per bar, aligned
    with the input list (same length and order) so it composes cleanly
    with strategies the same way SMA arrays do.
    """
    if window <= 0:
        raise ValueError("window must be positive")

    result: List[Dict[str, float]] = []
    for i in range(len(bars)):
        start = max(0, i - window + 1)
        segment = bars[start : i + 1]
        result.append(
            {
                "support": min(b.low for b in segment),
                "resistance": max(b.high for b in segment),
            }
        )
    return result


def simple_moving_average(values: List[float], period: int) -> List[Optional[float]]:
    """Simple moving average. None until `period` values are available.

    Public/reusable version - RSI, MACD and Bollinger Bands below all
    build on this same primitive instead of each re-deriving it.
    """
    if period <= 0:
        raise ValueError("period must be positive")

    result: List[Optional[float]] = [None] * len(values)
    window_sum = 0.0
    for i, value in enumerate(values):
        window_sum += value
        if i >= period:
            window_sum -= values[i - period]
        if i >= period - 1:
            result[i] = window_sum / period
    return result


def exponential_moving_average(values: List[float], period: int) -> List[Optional[float]]:
    """Exponential moving average, seeded with a plain SMA for the first
    value (the standard convention every charting platform uses)."""
    if period <= 0:
        raise ValueError("period must be positive")

    result: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return result

    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result[period - 1] = seed

    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        result[i] = prev
    return result


def _rolling_population_std(values: List[float], period: int) -> List[Optional[float]]:
    """Population standard deviation (ddof=0) over a trailing window -
    the convention used by Bollinger Bands on every mainstream platform."""
    result: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i < period - 1:
            continue
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / period
        result[i] = variance**0.5
    return result


def relative_strength_index(bars: List[Bar], period: int = 14) -> List[Optional[float]]:
    """
    Wilder's Relative Strength Index (RSI), the same smoothing method
    used by TradingView's built-in RSI indicator.

    Returns one value per bar (aligned, same length as `bars`), None
    for the warm-up period before `period` price changes exist.
    A reading above 70 conventionally flags "overbought", below 30
    flags "oversold" - RSIMeanReversionStrategy (see strategy.py) acts
    on exactly those thresholds.
    """
    if period <= 0:
        raise ValueError("period must be positive")

    n = len(bars)
    result: List[Optional[float]] = [None] * n
    if n <= period:
        return result

    closes = [b.close for b in bars]
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains[i] = max(change, 0.0)
        losses[i] = max(-change, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    result[period] = _rsi_from_averages(avg_gain, avg_loss)

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i] = _rsi_from_averages(avg_gain, avg_loss)

    return result


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0 and avg_loss == 0:
        return 50.0  # no price movement at all - neither overbought nor oversold
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


@dataclass(frozen=True)
class MACDPoint:
    """One bar's worth of MACD output. Fields are None during warm-up."""

    macd_line: Optional[float]
    signal_line: Optional[float]
    histogram: Optional[float]


def macd(
    bars: List[Bar], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> List[MACDPoint]:
    """
    Moving Average Convergence Divergence (MACD): the same 12/26/9
    default periods TradingView's built-in MACD uses.

    macd_line = EMA(fast) - EMA(slow)
    signal_line = EMA(macd_line, signal_period)
    histogram = macd_line - signal_line

    Returns one MACDPoint per bar, aligned with `bars`.
    """
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")

    closes = [b.close for b in bars]
    ema_fast = exponential_moving_average(closes, fast_period)
    ema_slow = exponential_moving_average(closes, slow_period)

    macd_values: List[Optional[float]] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]

    # Signal line is an EMA of the MACD line itself, but the MACD line
    # has a leading run of Nones (warm-up) that a plain EMA call can't
    # skip over, so we compute it on just the defined tail and splice
    # the result back into place at the correct offset.
    first_defined = next((i for i, v in enumerate(macd_values) if v is not None), None)
    signal_values: List[Optional[float]] = [None] * len(bars)
    if first_defined is not None:
        defined_macd = [v for v in macd_values[first_defined:] if v is not None]
        signal_tail = exponential_moving_average(defined_macd, signal_period)
        for offset, value in enumerate(signal_tail):
            signal_values[first_defined + offset] = value

    return [
        MACDPoint(
            macd_line=m,
            signal_line=s,
            histogram=(m - s) if m is not None and s is not None else None,
        )
        for m, s in zip(macd_values, signal_values)
    ]


@dataclass(frozen=True)
class BollingerBand:
    """One bar's worth of Bollinger Bands output. None during warm-up."""

    middle: Optional[float]
    upper: Optional[float]
    lower: Optional[float]


def bollinger_bands(
    bars: List[Bar], period: int = 20, num_std: float = 2.0
) -> List[BollingerBand]:
    """
    Bollinger Bands: a moving average (the middle band) plus/minus
    `num_std` standard deviations (the same 20-period/2-std defaults
    TradingView's built-in indicator uses).

    Returns one BollingerBand per bar, aligned with `bars`.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if num_std <= 0:
        raise ValueError("num_std must be positive")

    closes = [b.close for b in bars]
    middle = simple_moving_average(closes, period)
    std = _rolling_population_std(closes, period)

    bands: List[BollingerBand] = []
    for m, s in zip(middle, std):
        if m is None or s is None:
            bands.append(BollingerBand(middle=None, upper=None, lower=None))
        else:
            bands.append(BollingerBand(middle=m, upper=m + num_std * s, lower=m - num_std * s))
    return bands
