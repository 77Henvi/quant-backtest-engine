"""
Institutional Robustness & Stress-Testing Suite.

Provides:
1. Monte Carlo Equity Resampling & Confidence Ribbons (5th, 50th, 95th percentiles)
2. Ruin Probability & Drawdown Distribution Analysis
3. Walk-Forward / Parameter Sensitivity Grid Testing
"""

import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .models import BacktestResult, EquityPoint, Trade


@dataclass(frozen=True)
class MonteCarloSummary:
    """Summary statistics from a Monte Carlo simulation run."""

    iterations: int
    median_final_equity: float
    percentile_5th_final_equity: float
    percentile_95th_final_equity: float
    median_max_drawdown_pct: float
    percentile_95th_max_drawdown_pct: float  # worst-case drawdown (95th percentile)
    probability_of_ruin_pct: float  # probability of losing > 50% capital
    confidence_ribbon: List[Dict[str, float]]  # step-by-step percentile envelopes


def run_monte_carlo_simulation(
    result: BacktestResult,
    iterations: int = 1000,
    ruin_threshold_fraction: float = 0.5,
    seed: Optional[int] = 42,
) -> MonteCarloSummary:
    """
    Simulate thousands of possible trade sequence paths to test if the strategy's
    success was order-dependent or genuinely robust.
    """
    if seed is not None:
        random.seed(seed)

    if not result.trades or len(result.trades) < 2:
        return MonteCarloSummary(
            iterations=iterations,
            median_final_equity=result.final_equity,
            percentile_5th_final_equity=result.final_equity,
            percentile_95th_final_equity=result.final_equity,
            median_max_drawdown_pct=0.0,
            percentile_95th_max_drawdown_pct=0.0,
            probability_of_ruin_pct=0.0,
            confidence_ribbon=[],
        )

    trade_returns = [t.return_pct for t in result.trades]
    n_trades = len(trade_returns)
    init_cap = result.initial_capital
    ruin_capital = init_cap * ruin_threshold_fraction

    all_final_equities: List[float] = []
    all_max_drawdowns: List[float] = []
    ruin_count = 0
    simulated_curves: List[List[float]] = []

    for _ in range(iterations):
        # Bootstrap resample trade returns with replacement
        sample_returns = [random.choice(trade_returns) for _ in range(n_trades)]
        current_equity = init_cap
        curve = [current_equity]
        peak = current_equity
        max_dd = 0.0
        hit_ruin = False

        for ret in sample_returns:
            current_equity *= 1.0 + ret
            curve.append(current_equity)
            peak = max(peak, current_equity)
            if peak > 0:
                dd = (peak - current_equity) / peak
                max_dd = max(max_dd, dd)
            if current_equity <= ruin_capital:
                hit_ruin = True

        all_final_equities.append(current_equity)
        all_max_drawdowns.append(max_dd * 100)
        simulated_curves.append(curve)
        if hit_ruin:
            ruin_count += 1

    all_final_equities.sort()
    all_max_drawdowns.sort()

    p5_idx = int(0.05 * iterations)
    p50_idx = int(0.50 * iterations)
    p95_idx = int(0.95 * iterations)

    # Compute step-by-step confidence ribbons across all trade steps
    ribbon: List[Dict[str, float]] = []
    for step_i in range(n_trades + 1):
        step_equities = sorted(c[step_i] for c in simulated_curves)
        ribbon.append(
            {
                "step": float(step_i),
                "p5": step_equities[p5_idx],
                "p25": step_equities[int(0.25 * iterations)],
                "p50": step_equities[p50_idx],
                "p75": step_equities[int(0.75 * iterations)],
                "p95": step_equities[p95_idx],
            }
        )

    return MonteCarloSummary(
        iterations=iterations,
        median_final_equity=all_final_equities[p50_idx],
        percentile_5th_final_equity=all_final_equities[p5_idx],
        percentile_95th_final_equity=all_final_equities[p95_idx],
        median_max_drawdown_pct=all_max_drawdowns[p50_idx],
        percentile_95th_max_drawdown_pct=all_max_drawdowns[p95_idx],
        probability_of_ruin_pct=(ruin_count / iterations) * 100,
        confidence_ribbon=ribbon,
    )
