from datetime import date, timedelta
import math
import pytest

from app.domain.engine import BacktestEngine
from app.domain.models import Bar, EquityPoint, Signal, Trade
from app.domain.metrics import (
    compute_metrics,
    probabilistic_sharpe_ratio,
    _sortino_ratio,
    _omega_ratio,
    _value_at_risk,
    _alpha_beta,
    _max_drawdown_stats,
)


def make_bars(prices):
    start = date(2024, 1, 1)
    return [
        Bar(date=start + timedelta(days=i), open=p, high=p * 1.01, low=p * 0.99, close=p)
        for i, p in enumerate(prices)
    ]


class TestInstitutionalMetrics:
    def test_sortino_ratio_positive_for_upward_trend(self):
        returns = [0.01, 0.02, 0.015, -0.005, 0.012, 0.018]
        sortino = _sortino_ratio(returns, risk_free_rate=0.0)
        assert sortino > 0.0

    def test_sortino_zero_or_inf_edge_cases(self):
        all_positive = [0.01, 0.02, 0.03]
        sortino_inf = _sortino_ratio(all_positive, risk_free_rate=0.0)
        assert sortino_inf == math.inf

        all_negative = [-0.01, -0.02, -0.03]
        sortino_neg = _sortino_ratio(all_negative, risk_free_rate=0.0)
        assert sortino_neg < 0.0

    def test_omega_ratio(self):
        returns = [0.02, 0.03, -0.01, -0.01]
        omega = _omega_ratio(returns, threshold=0.0)
        assert omega == pytest.approx(0.05 / 0.02)

    def test_value_at_risk_and_cvar(self):
        # 100 observations
        returns = [0.01] * 95 + [-0.05, -0.06, -0.07, -0.08, -0.09]
        var_95, cvar_95 = _value_at_risk(returns, confidence=0.95)
        assert var_95 >= 5.0
        assert cvar_95 >= var_95

    def test_alpha_beta_calculation(self):
        bench_ret = [0.01, 0.02, -0.01, 0.015, -0.005, 0.02]
        # Strategy has 1.5x beta and 0.01 excess return
        strat_ret = [b * 1.5 + 0.005 for b in bench_ret]
        alpha, beta = _alpha_beta(strat_ret, bench_ret, risk_free_rate=0.0)
        assert beta == pytest.approx(1.5, rel=1e-2)
        assert alpha > 0.0

    def test_probabilistic_sharpe_ratio(self):
        start = date(2024, 1, 1)
        equity = [1000.0 * (1.005**i) for i in range(100)]
        curve = [EquityPoint(date=start + timedelta(days=i), equity=e) for i, e in enumerate(equity)]
        psr = probabilistic_sharpe_ratio(curve, benchmark_sharpe=0.0)
        assert 0.5 < psr <= 1.0

    def test_drawdown_duration_tracking(self):
        start = date(2024, 1, 1)
        equities = [100, 110, 105, 102, 108, 115, 112, 120]
        curve = [EquityPoint(date=start + timedelta(days=i), equity=e) for i, e in enumerate(equities)]
        max_dd, max_dur = _max_drawdown_stats(curve)
        assert max_dur == 3  # 105, 102, 108 are below the previous peak of 110
