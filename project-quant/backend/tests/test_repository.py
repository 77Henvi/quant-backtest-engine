import math

from app.infrastructure.repository import _json_safe_metrics


class TestJsonSafeMetrics:
    def test_finite_values_pass_through_unchanged(self):
        metrics = {"sharpe_ratio": 1.5, "num_trades": 3.0, "win_rate_pct": 66.6}
        assert _json_safe_metrics(metrics) == metrics

    def test_positive_infinity_becomes_none(self):
        metrics = {"profit_factor": math.inf}
        assert _json_safe_metrics(metrics) == {"profit_factor": None}

    def test_negative_infinity_becomes_none(self):
        metrics = {"weird_metric": -math.inf}
        assert _json_safe_metrics(metrics) == {"weird_metric": None}

    def test_nan_becomes_none(self):
        metrics = {"broken_metric": math.nan}
        assert _json_safe_metrics(metrics) == {"broken_metric": None}

    def test_mixed_dict_only_sanitizes_the_unsafe_entries(self):
        metrics = {"sharpe_ratio": 1.2, "profit_factor": math.inf, "num_trades": 5.0}
        result = _json_safe_metrics(metrics)
        assert result["sharpe_ratio"] == 1.2
        assert result["profit_factor"] is None
        assert result["num_trades"] == 5.0

    def test_zero_is_not_mistaken_for_unsafe(self):
        metrics = {"total_return_pct": 0.0}
        assert _json_safe_metrics(metrics) == {"total_return_pct": 0.0}
