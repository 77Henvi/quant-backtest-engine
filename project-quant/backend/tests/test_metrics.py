import math
from datetime import date, timedelta

import pytest

from app.domain.metrics import compute_metrics
from app.domain.models import BacktestResult, EquityPoint, Trade


def make_equity_curve(values):
    start = date(2024, 1, 1)
    return [EquityPoint(date=start + timedelta(days=i), equity=v) for i, v in enumerate(values)]


class TestComputeMetrics:
    def test_no_trades_gives_zeroed_metrics(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1000, 1000]),
            initial_capital=1000,
            final_equity=1000,
        )
        metrics = compute_metrics(result)
        assert metrics["num_trades"] == 0
        assert metrics["win_rate_pct"] == 0.0
        assert metrics["profit_factor"] == 0.0
        assert metrics["total_return_pct"] == 0.0

    def test_total_return_pct(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1100, 1200]),
            initial_capital=1000,
            final_equity=1200,
        )
        metrics = compute_metrics(result)
        assert metrics["total_return_pct"] == pytest.approx(20.0)

    def test_win_rate_and_profit_factor(self):
        trades = [
            Trade(date(2024, 1, 1), 100, 10, date(2024, 1, 2), 110),  # win: +100
            Trade(date(2024, 1, 3), 100, 10, date(2024, 1, 4), 90),  # loss: -100
            Trade(date(2024, 1, 5), 100, 10, date(2024, 1, 6), 120),  # win: +200
        ]
        result = BacktestResult(
            trades=trades,
            equity_curve=make_equity_curve([1000, 1200]),
            initial_capital=1000,
            final_equity=1200,
        )
        metrics = compute_metrics(result)
        assert metrics["num_trades"] == 3
        assert metrics["win_rate_pct"] == pytest.approx(200 / 3)
        # gross profit = 300, gross loss = 100 -> profit factor 3.0
        assert metrics["profit_factor"] == pytest.approx(3.0)

    def test_profit_factor_is_infinite_with_no_losses(self):
        trades = [Trade(date(2024, 1, 1), 100, 10, date(2024, 1, 2), 110)]
        result = BacktestResult(
            trades=trades,
            equity_curve=make_equity_curve([1000, 1100]),
            initial_capital=1000,
            final_equity=1100,
        )
        metrics = compute_metrics(result)
        assert math.isinf(metrics["profit_factor"])

    def test_max_drawdown_detects_peak_to_trough(self):
        # Peaks at 1200, troughs at 900 -> drawdown = (1200-900)/1200 = 25%
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1200, 900, 1100]),
            initial_capital=1000,
            final_equity=1100,
        )
        metrics = compute_metrics(result)
        assert metrics["max_drawdown_pct"] == pytest.approx(25.0)

    def test_max_drawdown_zero_when_monotonically_increasing(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1050, 1100, 1200]),
            initial_capital=1000,
            final_equity=1200,
        )
        metrics = compute_metrics(result)
        assert metrics["max_drawdown_pct"] == 0.0

    def test_sharpe_ratio_zero_for_flat_equity(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1000, 1000, 1000]),
            initial_capital=1000,
            final_equity=1000,
        )
        metrics = compute_metrics(result)
        assert metrics["sharpe_ratio"] == 0.0

    def test_sharpe_ratio_positive_for_steady_gains(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1010, 1020, 1030, 1040, 1050]),
            initial_capital=1000,
            final_equity=1050,
        )
        metrics = compute_metrics(result)
        assert metrics["sharpe_ratio"] > 0

    def test_handles_too_few_points_for_sharpe(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_equity_curve([1000, 1010]),
            initial_capital=1000,
            final_equity=1010,
        )
        metrics = compute_metrics(result)
        assert metrics["sharpe_ratio"] == 0.0
