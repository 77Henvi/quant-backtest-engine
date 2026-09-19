from datetime import date, timedelta
from typing import List

import pytest

from app.domain.engine import BacktestEngine
from app.domain.models import Bar, Signal
from app.domain.strategy import Strategy


def make_bars(closes: List[float]) -> List[Bar]:
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c, low=c, close=c)
        for i, c in enumerate(closes)
    ]


class ScriptedStrategy(Strategy):
    """A strategy that plays back a fixed, hand-written list of signals.

    Used to test the engine in isolation from any real signal-generation
    logic - it lets a test say exactly "buy on bar 0, sell on bar 2" and
    verify the engine's bookkeeping is correct.
    """

    def __init__(self, signals: List[Signal]):
        self._signals = signals

    def generate_signals(self, bars: List[Bar]) -> List[Signal]:
        return self._signals


class TestBacktestEngineConstruction:
    def test_rejects_non_positive_capital(self):
        with pytest.raises(ValueError):
            BacktestEngine(initial_capital=0)

    def test_rejects_invalid_position_fraction(self):
        with pytest.raises(ValueError):
            BacktestEngine(position_fraction=0)
        with pytest.raises(ValueError):
            BacktestEngine(position_fraction=1.5)


class TestBacktestEngineRun:
    def test_empty_bars_returns_flat_result(self):
        engine = BacktestEngine(initial_capital=10_000)
        result = engine.run([], ScriptedStrategy([]))
        assert result.trades == []
        assert result.equity_curve == []
        assert result.final_equity == 10_000

    def test_mismatched_signal_count_raises(self):
        engine = BacktestEngine()
        bars = make_bars([10, 11, 12])
        with pytest.raises(ValueError):
            engine.run(bars, ScriptedStrategy([Signal.HOLD]))

    def test_buy_then_sell_produces_one_closed_trade(self):
        engine = BacktestEngine(initial_capital=1_000, position_fraction=1.0)
        bars = make_bars([100, 110, 120])
        signals = [Signal.BUY, Signal.HOLD, Signal.SELL]

        result = engine.run(bars, ScriptedStrategy(signals))

        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.entry_price == 100
        assert trade.exit_price == 120
        assert trade.is_open is False
        # All-in at 100, sold at 120 -> 20% gain on full capital.
        assert result.final_equity == pytest.approx(1_200)

    def test_open_position_is_force_closed_at_end(self):
        engine = BacktestEngine(initial_capital=1_000, position_fraction=1.0)
        bars = make_bars([100, 110, 120])
        signals = [Signal.BUY, Signal.HOLD, Signal.HOLD]  # never explicitly sold

        result = engine.run(bars, ScriptedStrategy(signals))

        assert len(result.trades) == 1
        assert result.trades[0].is_open is False
        assert result.trades[0].exit_price == 120
        assert result.final_equity == pytest.approx(1_200)

    def test_duplicate_buy_signals_do_not_open_second_position(self):
        engine = BacktestEngine(initial_capital=1_000, position_fraction=1.0)
        bars = make_bars([100, 100, 120])
        signals = [Signal.BUY, Signal.BUY, Signal.SELL]

        result = engine.run(bars, ScriptedStrategy(signals))

        assert len(result.trades) == 1

    def test_sell_with_no_open_position_is_a_no_op(self):
        engine = BacktestEngine(initial_capital=1_000)
        bars = make_bars([100, 110])
        signals = [Signal.SELL, Signal.HOLD]

        result = engine.run(bars, ScriptedStrategy(signals))

        assert result.trades == []
        assert result.final_equity == 1_000

    def test_position_fraction_limits_capital_deployed(self):
        engine = BacktestEngine(initial_capital=1_000, position_fraction=0.5)
        bars = make_bars([100, 100, 200])
        signals = [Signal.BUY, Signal.HOLD, Signal.SELL]

        result = engine.run(bars, ScriptedStrategy(signals))

        # Only 500 deployed (5 units at 100), 500 stays in cash the whole time.
        # 5 units sold at 200 = 1000, plus 500 cash never invested = 1500.
        assert result.final_equity == pytest.approx(1_500)

    def test_equity_curve_has_one_point_per_bar(self):
        engine = BacktestEngine(initial_capital=1_000)
        bars = make_bars([100, 105, 110, 108])
        signals = [Signal.BUY, Signal.HOLD, Signal.HOLD, Signal.SELL]

        result = engine.run(bars, ScriptedStrategy(signals))

        assert len(result.equity_curve) == len(bars)
        assert [p.date for p in result.equity_curve] == [b.date for b in bars]

    def test_full_pipeline_with_real_strategy(self):
        """Smoke test: engine + SmaCrossoverStrategy end to end."""
        from app.domain.strategy import SmaCrossoverStrategy

        closes = [10, 9, 8, 7, 6, 12, 14, 16, 18, 20, 19, 15, 10, 8]
        bars = make_bars(closes)
        strategy = SmaCrossoverStrategy(fast_period=2, slow_period=4)
        engine = BacktestEngine(initial_capital=10_000)

        result = engine.run(bars, strategy)

        assert result.initial_capital == 10_000
        assert isinstance(result.final_equity, float)
        assert len(result.equity_curve) == len(bars)
