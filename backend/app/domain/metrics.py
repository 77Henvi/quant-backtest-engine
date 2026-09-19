"""
Performance metrics computed from a BacktestResult.

Kept separate from engine.py on purpose: the engine's only job is to
simulate trades correctly, metrics' only job is to summarize them.
Adding a new metric never requires touching simulation logic, and vice
versa.
"""

import math
from statistics import NormalDist
from typing import Dict, List, Optional

from .models import BacktestResult, EquityPoint

TRADING_DAYS_PER_YEAR = 252

# Euler-Mascheroni constant, used by the Deflated Sharpe Ratio formula below.
_EULER_MASCHERONI = 0.5772156649015329


def compute_metrics(
    result: BacktestResult, num_trials: Optional[int] = None
) -> Dict[str, float]:
    """Compute the standard metrics for a backtest result.

    `num_trials` is optional: pass the number of strategy/parameter
    combinations you tried before picking this one to also get a
    `deflated_sharpe_ratio` entry (see `deflated_sharpe_ratio` below for
    why that number matters). Omit it if you only ran one backtest -
    the raw Sharpe ratio alone is fine in that case.
    """
    metrics: Dict[str, float] = {
        "total_return_pct": _total_return_pct(result),
        "num_trades": float(len(result.trades)),
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": _max_drawdown_pct(result.equity_curve),
        "sharpe_ratio": _sharpe_ratio(result.equity_curve),
    }

    if num_trials is not None:
        metrics["deflated_sharpe_ratio"] = deflated_sharpe_ratio(
            result.equity_curve, num_trials
        )

    if result.trades:
        wins = [t for t in result.trades if t.pnl > 0]
        losses = [t for t in result.trades if t.pnl < 0]

        metrics["win_rate_pct"] = len(wins) / len(result.trades) * 100

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        if gross_loss > 0:
            metrics["profit_factor"] = gross_profit / gross_loss
        elif gross_profit > 0:
            metrics["profit_factor"] = math.inf

    return metrics


def _total_return_pct(result: BacktestResult) -> float:
    if result.initial_capital <= 0:
        return 0.0
    return (result.final_equity - result.initial_capital) / result.initial_capital * 100


def _max_drawdown_pct(equity_curve: List[EquityPoint]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].equity
    max_dd = 0.0
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            drawdown = (peak - point.equity) / peak
            max_dd = max(max_dd, drawdown)
    return max_dd * 100


def _sharpe_ratio(equity_curve: List[EquityPoint], risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio computed from daily equity returns."""
    if len(equity_curve) < 3:
        return 0.0

    returns: List[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        curr = equity_curve[i].equity
        if prev > 0:
            returns.append((curr - prev) / prev)

    if len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0.0

    daily_sharpe = (mean_return - risk_free_rate) / std_dev
    return daily_sharpe * math.sqrt(TRADING_DAYS_PER_YEAR)


def _period_returns(equity_curve: List[EquityPoint]) -> List[float]:
    returns: List[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        curr = equity_curve[i].equity
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _skewness(values: List[float], mean: float, std: float) -> float:
    n = len(values)
    if std == 0 or n == 0:
        return 0.0
    return sum((v - mean) ** 3 for v in values) / n / std**3


def _pearson_kurtosis(values: List[float], mean: float, std: float) -> float:
    """Raw (non-excess) kurtosis - a normal distribution scores 3.0 here,
    matching the convention the Deflated Sharpe Ratio formula expects."""
    n = len(values)
    if std == 0 or n == 0:
        return 3.0
    return sum((v - mean) ** 4 for v in values) / n / std**4


def deflated_sharpe_ratio(
    equity_curve: List[EquityPoint],
    num_trials: int,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    A raw Sharpe ratio answers "was this profitable, adjusted for
    volatility?". It does NOT answer a different, more dangerous
    question: "did I just get lucky by trying enough strategies until
    one of them looked good?" Test a thousand random trading rules on
    the same price history and the best one will have an excellent
    Sharpe ratio by pure chance - that Sharpe measures how many things
    you tried, not how good the strategy is.

    The DSR corrects for this. Given how many strategies/parameter
    combinations (`num_trials`) were tried before this one was picked,
    it returns the probability (0 to 1) that the observed Sharpe ratio
    reflects genuine skill rather than the best outcome of pure noise.
    A DSR near 1.0 means the result is very likely real. A DSR at or
    below 0.5 means it is statistically indistinguishable from what
    you'd expect by chance alone, given the size of the search.

    Reference: "The Deflated Sharpe Ratio: Correcting for Selection
    Bias, Backtest Overfitting and Non-Normality", Journal of Portfolio
    Management (2014).
    """
    if num_trials < 2:
        raise ValueError(
            "num_trials must be at least 2 - the DSR corrects for a search "
            "over multiple trials, so it needs to know how many were tried"
        )

    returns = _period_returns(equity_curve)
    t = len(returns)
    if t < 3:
        return 0.0  # not enough data to say anything meaningful

    mean_return = sum(returns) / t
    variance = sum((r - mean_return) ** 2 for r in returns) / (t - 1)
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return 0.0  # zero variance - no meaningful Sharpe to deflate

    sr_hat = (mean_return - risk_free_rate) / std_dev
    skew = _skewness(returns, mean_return, std_dev)
    kurt = _pearson_kurtosis(returns, mean_return, std_dev)

    # Variance of the Sharpe ratio estimator itself, adjusted for
    # non-normal (skewed/fat-tailed) returns. This term also appears as
    # the denominator below, so guard it once here.
    variance_term = 1 - skew * sr_hat + (kurt - 1) / 4 * sr_hat**2
    variance_term = max(variance_term, 1e-12)  # keep sqrt() well-defined

    sigma_sr = math.sqrt(variance_term / (t - 1))

    # Expected maximum Sharpe ratio you'd see across `num_trials`
    # independent trials of pure noise (the "haircut" to apply).
    normal = NormalDist()
    z1 = normal.inv_cdf(1 - 1 / num_trials)
    z2 = normal.inv_cdf(1 - 1 / (num_trials * math.e))
    sr_expected_max = sigma_sr * ((1 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)

    numerator = (sr_hat - sr_expected_max) * math.sqrt(t - 1)
    denominator = math.sqrt(variance_term)
    return normal.cdf(numerator / denominator)
