"""
Strategy interface + one concrete example strategy.

New strategies plug in by subclassing `Strategy` and implementing
`generate_signals`. The engine only ever talks to this interface, so
adding a new strategy never requires touching engine.py.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .indicators import fibonacci_retracement_levels, find_swing_range, relative_strength_index
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
    and derive Fibonacci levels from it (same math TradingView's
    Fibonacci Retracement drawing tool uses).

    - BUY  when price bounces up through the deep retracement level
      (default 61.8%) - i.e. the pullback found support.
    - SELL (take profit) when price recovers up through the shallow
      retracement level (default 23.6%) - i.e. it's back near the swing high.
    - SELL (stop loss) if price instead breaks below the swing low -
      the "support" failed, so we cut the loss instead of holding.
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

    - BUY  when RSI recovers back above the oversold threshold (default
      30) from below - the pullback found a floor.
    - SELL (take profit) when RSI reaches the overbought threshold
      (default 70).
    - SELL (stop loss) if RSI instead drops back below the deep
      threshold (default 20) - the "floor" failed, cut the loss instead
      of waiting for a recovery that isn't happening.
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
