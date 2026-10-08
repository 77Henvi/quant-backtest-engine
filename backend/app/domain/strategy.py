"""
Strategy interface + concrete institutional trading strategies.

New strategies plug in by subclassing `Strategy` and implementing
`generate_signals`. The engine only ever talks to this interface, so
adding a new strategy never requires touching engine.py.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .indicators import (
    bollinger_bands,
    exponential_moving_average,
    fibonacci_retracement_levels,
    find_swing_range,
    macd,
    relative_strength_index,
)
from .models import Bar, Signal


class Strategy(ABC):
    """Base class every trading strategy must implement."""

    @abstractmethod
    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        """
        Return exactly one Signal per bar, in the same order as `bars`.

        Implementations must be pure functions of `bars` (no hidden
        state carried between calls) so backtest runs are reproducible.
        """
        raise NotImplementedError


class SmaCrossoverStrategy(Strategy):
    """
    Classic moving-average crossover.

    BUY  when the fast SMA crosses above the slow SMA.
    SELL when the fast SMA crosses below the slow SMA.
    HOLD otherwise (including the warm-up period where the slow SMA
    isn't defined yet).
    """

    def __init__(self, fast_period: int = 5, slow_period: int = 20):
        if fast_period <= 0 or slow_period <= 0:
            raise ValueError("periods must be positive integers")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        closes = [b.close for b in bars]
        fast_sma = self._sma(closes, self.fast_period)
        slow_sma = self._sma(closes, self.slow_period)

        signals: List[Signal] = [Signal.HOLD] * len(bars)
        prev_state: Optional[str] = None

        for i in range(len(bars)):
            if fast_sma[i] is None or slow_sma[i] is None:
                continue

            state = "above" if fast_sma[i] > slow_sma[i] else "below"

            if prev_state == "below" and state == "above":
                signals[i] = Signal.BUY
            elif prev_state == "above" and state == "below":
                signals[i] = Signal.SELL

            prev_state = state

        return signals

    @staticmethod
    def _sma(values: List[float], period: int) -> List[Optional[float]]:
        """Simple moving average. None until `period` values are available."""
        result: List[Optional[float]] = [None] * len(values)
        window_sum = 0.0
        for i, value in enumerate(values):
            window_sum += value
            if i >= period:
                window_sum -= values[i - period]
            if i >= period - 1:
                result[i] = window_sum / period
        return result


class FibonacciRetracementStrategy(Strategy):
    """
    Buy-the-dip strategy using Fibonacci retracement levels.

    For each bar, look back `lookback` bars to find the swing high/low
    and derive Fibonacci levels from it.

    - BUY  when price bounces up through the deep retracement level (default 61.8%)
    - SELL (take profit) when price recovers up through the shallow retracement level (default 23.6%)
    - SELL (stop loss) if price breaks below the swing low
    """

    def __init__(self, lookback: int = 20, entry_level: float = 0.618, exit_level: float = 0.236):
        if lookback <= 1:
            raise ValueError("lookback must be greater than 1")
        if not (0.0 < exit_level < entry_level < 1.0):
            raise ValueError("must satisfy 0 < exit_level < entry_level < 1")
        self.lookback = lookback
        self.entry_level = entry_level
        self.exit_level = exit_level

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        signals: List[Signal] = [Signal.HOLD] * len(bars)
        holding = False

        for i in range(len(bars)):
            if i < self.lookback - 1:
                continue

            window = bars[i - self.lookback + 1 : i + 1]
            swing = find_swing_range(window, lookback=self.lookback)
            if swing.swing_high == swing.swing_low:
                continue  # no volatility in this window - nothing to retrace

            levels = fibonacci_retracement_levels(swing, uptrend=True)
            entry_price = levels[self.entry_level]
            exit_price = levels[self.exit_level]
            close = bars[i].close

            if not holding and close >= entry_price:
                signals[i] = Signal.BUY
                holding = True
            elif holding and (close >= exit_price or close <= swing.swing_low):
                signals[i] = Signal.SELL
                holding = False

        return signals


class RSIMeanReversionStrategy(Strategy):
    """
    Mean-reversion strategy driven by the Relative Strength Index (RSI).

    - BUY  when RSI recovers back above oversold threshold (default 30) from below.
    - SELL (take profit) when RSI reaches overbought threshold (default 70).
    - SELL (stop loss) if RSI drops back below deep oversold threshold (default 20).
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        deep_oversold: float = 20.0,
    ):
        if not (0 < deep_oversold < oversold < overbought < 100):
            raise ValueError("must satisfy 0 < deep_oversold < oversold < overbought < 100")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.deep_oversold = deep_oversold

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        rsi_values = relative_strength_index(bars, period=self.period)
        signals: List[Signal] = [Signal.HOLD] * len(bars)
        holding = False
        prev_rsi: Optional[float] = None

        for i, rsi in enumerate(rsi_values):
            if rsi is None:
                continue

            if prev_rsi is not None:
                if not holding and prev_rsi < self.oversold and rsi >= self.oversold:
                    signals[i] = Signal.BUY
                    holding = True
                elif holding and (rsi >= self.overbought or rsi <= self.deep_oversold):
                    signals[i] = Signal.SELL
                    holding = False

            prev_rsi = rsi

        return signals


class MACDCrossoverStrategy(Strategy):
    """
    Trend-following momentum strategy based on MACD line and Signal line crossover.

    - BUY  when MACD line crosses above Signal line.
    - SELL when MACD line crosses below Signal line.
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
            raise ValueError("All MACD periods must be positive integers")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        macd_points = macd(
            bars,
            fast_period=self.fast_period,
            slow_period=self.slow_period,
            signal_period=self.signal_period,
        )
        signals: List[Signal] = [Signal.HOLD] * len(bars)
        holding = False
        prev_macd: Optional[float] = None
        prev_sig: Optional[float] = None

        for i, pt in enumerate(macd_points):
            if pt.macd_line is None or pt.signal_line is None:
                continue

            if prev_macd is not None and prev_sig is not None:
                # Bullish crossover
                if not holding and prev_macd <= prev_sig and pt.macd_line > pt.signal_line:
                    signals[i] = Signal.BUY
                    holding = True
                # Bearish crossover
                elif holding and prev_macd >= prev_sig and pt.macd_line < pt.signal_line:
                    signals[i] = Signal.SELL
                    holding = False

            prev_macd = pt.macd_line
            prev_sig = pt.signal_line

        return signals


class BollingerMeanReversionStrategy(Strategy):
    """
    Volatility & Mean-Reversion strategy using Bollinger Bands.

    - BUY  when price closes below the lower band and then closes back inside.
    - SELL (take profit) when price crosses above the middle band (or upper band).
    - SELL (stop loss) if price drops significantly below the lower band (e.g. 2x band width).
    """

    def __init__(self, period: int = 20, num_std: float = 2.0, exit_at_upper: bool = False):
        if period <= 0:
            raise ValueError("period must be positive")
        if num_std <= 0:
            raise ValueError("num_std must be positive")
        self.period = period
        self.num_std = num_std
        self.exit_at_upper = exit_at_upper

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        bands = bollinger_bands(bars, period=self.period, num_std=self.num_std)
        signals: List[Signal] = [Signal.HOLD] * len(bars)
        holding = False
        was_below_lower = False

        for i, (bar, band) in enumerate(zip(bars, bands)):
            if band.middle is None or band.upper is None or band.lower is None:
                continue

            close = bar.close
            # Check bounce from below lower band
            if not holding:
                if close < band.lower:
                    was_below_lower = True
                elif was_below_lower and close >= band.lower:
                    signals[i] = Signal.BUY
                    holding = True
                    was_below_lower = False
            else:
                target_exit = band.upper if self.exit_at_upper else band.middle
                if close >= target_exit:
                    signals[i] = Signal.SELL
                    holding = False
                    was_below_lower = False
                elif close < (band.lower - (band.upper - band.middle)):  # stop loss
                    signals[i] = Signal.SELL
                    holding = False
                    was_below_lower = False

        return signals


class DualMomentumStrategy(Strategy):
    """
    Multi-Indicator Institutional Strategy combining RSI with EMA Trend Filter.

    - Trend Filter: Only trade in the direction of the long-term trend (Price > EMA).
    - Entry: Buy when RSI pulls back into oversold zone and recovers.
    - Exit: Sell when RSI reaches overbought or price breaks below EMA trend filter.
    """

    def __init__(self, ema_period: int = 50, rsi_period: int = 14, rsi_entry: float = 35.0, rsi_exit: float = 65.0):
        if ema_period <= 0 or rsi_period <= 0:
            raise ValueError("Periods must be positive integers")
        if not (0 < rsi_entry < rsi_exit < 100):
            raise ValueError("Must satisfy 0 < rsi_entry < rsi_exit < 100")
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.rsi_entry = rsi_entry
        self.rsi_exit = rsi_exit

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        closes = [b.close for b in bars]
        ema_values = exponential_moving_average(closes, self.ema_period)
        rsi_values = relative_strength_index(bars, self.rsi_period)

        signals: List[Signal] = [Signal.HOLD] * len(bars)
        holding = False
        prev_rsi: Optional[float] = None

        for i in range(len(bars)):
            ema = ema_values[i]
            rsi = rsi_values[i]
            close = bars[i].close

            if ema is None or rsi is None:
                continue

            if prev_rsi is not None:
                # Uptrend confirmed by EMA + RSI bounce
                if not holding and close > ema and prev_rsi < self.rsi_entry and rsi >= self.rsi_entry:
                    signals[i] = Signal.BUY
                    holding = True
                elif holding and (rsi >= self.rsi_exit or close < ema * 0.98):
                    signals[i] = Signal.SELL
                    holding = False

            prev_rsi = rsi

        return signals
