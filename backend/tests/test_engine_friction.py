from datetime import date, timedelta
import pytest

from app.domain.engine import BacktestEngine
from app.domain.models import Bar, Signal, Trade
from app.domain.robustness import run_monte_carlo_simulation
from app.domain.strategy import Strategy


def make_bars(closes):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=c, high=c * 1.01, low=c * 0.99, close=c)
        for i, c in enumerate(closes)
    ]


class ScriptedStrategy(Strategy):
    def __init__(self, signals):
        self._signals = signals

    def generate_signals(self, bars):
        return self._signals


class TestEngineFriction:
    def test_commission_reduces_equity(self):
        engine_no_comm = BacktestEngine(initial_capital=1000, commission_rate=0.0)
        engine_with_comm = BacktestEngine(initial_capital=1000, commission_rate=0.01)  # 1% comm

        bars = make_bars([100, 110, 120])
        signals = [Signal.BUY, Signal.HOLD, Signal.SELL]

        res_no = engine_no_comm.run(bars, ScriptedStrategy(signals))
        res_comm = engine_with_comm.run(bars, ScriptedStrategy(signals))

        assert res_comm.final_equity < res_no.final_equity
        assert res_comm.trades[0].commission > 0

    def test_slippage_penalizes_entry_and_exit(self):
        engine_no_slip = BacktestEngine(initial_capital=1000, slippage_rate=0.0)
        engine_with_slip = BacktestEngine(initial_capital=1000, slippage_rate=0.01)  # 1% slippage

        bars = make_bars([100, 110, 120])
        signals = [Signal.BUY, Signal.HOLD, Signal.SELL]

        res_no = engine_no_slip.run(bars, ScriptedStrategy(signals))
        res_slip = engine_with_slip.run(bars, ScriptedStrategy(signals))

        assert res_slip.trades[0].entry_price > 100.0
        assert res_slip.trades[0].exit_price < 120.0
        assert res_slip.final_equity < res_no.final_equity


class TestMonteCarloSimulation:
    def test_monte_carlo_with_sample_trades(self):
        engine = BacktestEngine(initial_capital=1000)
        bars = make_bars([100, 110, 100, 110, 100, 110, 100, 110])
        signals = [Signal.BUY, Signal.SELL, Signal.BUY, Signal.SELL, Signal.BUY, Signal.SELL, Signal.BUY, Signal.SELL]

        result = engine.run(bars, ScriptedStrategy(signals))
        mc = run_monte_carlo_simulation(result, iterations=500, seed=42)

        assert mc.iterations == 500
        assert mc.percentile_5th_final_equity <= mc.median_final_equity <= mc.percentile_95th_final_equity
        assert len(mc.confidence_ribbon) > 0
