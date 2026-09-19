from datetime import date, timedelta

import pytest

from app.domain.metrics import compute_metrics, deflated_sharpe_ratio
from app.domain.models import BacktestResult, EquityPoint


def make_equity_curve(values):
    start = date(2024, 1, 1)
    return [EquityPoint(date=start + timedelta(days=i), equity=v) for i, v in enumerate(values)]


def make_noisy_uptrend_curve(num_points=40, start_equity=1000.0):
    """Deterministic (no randomness) equity curve with a positive drift
    and some noise, so skewness/kurtosis aren't trivially zero - this
    exercises the DSR's non-normality correction, not just the happy path."""
    daily_returns = [0.01, -0.004, 0.015, 0.002, -0.006, 0.012, 0.008, -0.003]
    equity = start_equity
    values = [equity]
    for i in range(num_points - 1):
        equity *= 1 + daily_returns[i % len(daily_returns)]
        values.append(equity)
    return make_equity_curve(values)


class TestDeflatedSharpeRatio:
    def test_rejects_fewer_than_two_trials(self):
        curve = make_noisy_uptrend_curve()
        with pytest.raises(ValueError):
            deflated_sharpe_ratio(curve, num_trials=1)
        with pytest.raises(ValueError):
            deflated_sharpe_ratio(curve, num_trials=0)

    def test_too_few_data_points_returns_zero(self):
        curve = make_equity_curve([1000, 1010])  # only 1 return observation
        assert deflated_sharpe_ratio(curve, num_trials=10) == 0.0

    def test_zero_variance_curve_returns_zero(self):
        curve = make_equity_curve([1000, 1000, 1000, 1000, 1000])
        assert deflated_sharpe_ratio(curve, num_trials=10) == 0.0

    def test_result_is_a_valid_probability(self):
        curve = make_noisy_uptrend_curve()
        dsr = deflated_sharpe_ratio(curve, num_trials=50)
        assert 0.0 <= dsr <= 1.0

    def test_more_trials_lowers_the_deflated_sharpe(self):
        """The core point of the DSR: searching harder for a good result
        should make the same track record look less impressive."""
        curve = make_noisy_uptrend_curve()
        dsr_few_trials = deflated_sharpe_ratio(curve, num_trials=2)
        dsr_many_trials = deflated_sharpe_ratio(curve, num_trials=1000)
        assert dsr_many_trials < dsr_few_trials

    def test_single_trial_equivalent_is_more_believable_than_thousand_trial_search(self):
        """A strategy that was the ONE thing you tried should look far
        more credible than the best of a thousand random attempts, even
        with an identical track record."""
        curve = make_noisy_uptrend_curve()
        honest_dsr = deflated_sharpe_ratio(curve, num_trials=2)
        overfit_dsr = deflated_sharpe_ratio(curve, num_trials=10_000)
        # A huge search should be able to drag a merely-decent track
        # record's credibility down substantially.
        assert overfit_dsr < honest_dsr - 0.05

    def test_flat_noisy_curve_with_no_edge_scores_low(self):
        """A strategy with no real drift shouldn't score as 'definitely
        skillful' regardless of trial count."""
        # Returns that average out to roughly zero net drift.
        values = [1000, 1010, 995, 1005, 992, 1008, 998, 1003, 997, 1000]
        curve = make_equity_curve(values)
        dsr = deflated_sharpe_ratio(curve, num_trials=100)
        assert dsr < 0.9

    def test_compute_metrics_without_num_trials_omits_dsr(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_noisy_uptrend_curve(),
            initial_capital=1000,
            final_equity=1100,
        )
        metrics = compute_metrics(result)
        assert "deflated_sharpe_ratio" not in metrics

    def test_compute_metrics_with_num_trials_includes_dsr(self):
        result = BacktestResult(
            trades=[],
            equity_curve=make_noisy_uptrend_curve(),
            initial_capital=1000,
            final_equity=1100,
        )
        metrics = compute_metrics(result, num_trials=25)
        assert "deflated_sharpe_ratio" in metrics
        assert 0.0 <= metrics["deflated_sharpe_ratio"] <= 1.0
