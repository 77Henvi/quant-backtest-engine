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
    result: BacktestResult, num_trials: Optional[int] = None, risk_free_rate: float = 0.0
) -> Dict[str, float]:
    """Compute the full institutional suite of risk and return metrics.

    `num_trials` is optional: pass the number of strategy/parameter
    combinations you tried before picking this one to also get a
    `deflated_sharpe_ratio` entry.
    """
    returns = _period_returns(result.equity_curve)
    n_bars = len(result.equity_curve)
    years = n_bars / TRADING_DAYS_PER_YEAR if n_bars > 0 else 0.0

    total_ret = _total_return_pct(result)
    cagr = _cagr_pct(result.initial_capital, result.final_equity, years)
    max_dd, max_dd_duration = _max_drawdown_stats(result.equity_curve)
    ann_vol = _annualized_volatility_pct(returns)

    sharpe = _sharpe_ratio(result.equity_curve, risk_free_rate=risk_free_rate)
    sortino = _sortino_ratio(returns, risk_free_rate=risk_free_rate)
    calmar = (cagr / max_dd) if max_dd > 0 else (math.inf if cagr > 0 else 0.0)
    omega = _omega_ratio(returns, threshold=risk_free_rate / TRADING_DAYS_PER_YEAR)

    var_95, cvar_95 = _value_at_risk(returns, confidence=0.95)
    psr = probabilistic_sharpe_ratio(result.equity_curve, benchmark_sharpe=0.0)

    metrics: Dict[str, float] = {
        "total_return_pct": total_ret,
        "cagr_pct": cagr,
        "annualized_volatility_pct": ann_vol,
        "num_trades": float(len(result.trades)),
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": max_dd,
        "max_drawdown_duration_bars": float(max_dd_duration),
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "omega_ratio": omega,
        "var_95_pct": var_95,
        "cvar_95_pct": cvar_95,
        "probabilistic_sharpe_ratio": psr,
    }

    if num_trials is not None:
        metrics["deflated_sharpe_ratio"] = deflated_sharpe_ratio(
            result.equity_curve, num_trials, risk_free_rate=risk_free_rate
        )

    # Trade statistics
    if result.trades:
        wins = [t for t in result.trades if t.pnl > 0]
        losses = [t for t in result.trades if t.pnl < 0]
        n_trades = len(result.trades)

        win_rate = len(wins) / n_trades * 100
        metrics["win_rate_pct"] = win_rate

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        if gross_loss > 0:
            metrics["profit_factor"] = gross_profit / gross_loss
        elif gross_profit > 0:
            metrics["profit_factor"] = math.inf

        avg_win = (gross_profit / len(wins)) if wins else 0.0
        avg_loss = (gross_loss / len(losses)) if losses else 0.0
        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else (math.inf if avg_win > 0 else 0.0)
        metrics["payoff_ratio"] = payoff_ratio

        # Kelly Criterion fraction: K = W - (1 - W)/R
        p_win = len(wins) / n_trades
        if payoff_ratio > 0 and payoff_ratio != math.inf:
            kelly = p_win - ((1.0 - p_win) / payoff_ratio)
            metrics["kelly_criterion_pct"] = max(0.0, kelly * 100)
        else:
            metrics["kelly_criterion_pct"] = 0.0

    # Benchmark analytics (Alpha, Beta) if benchmark curve provided
    if result.benchmark_equity_curve and len(result.benchmark_equity_curve) == len(result.equity_curve):
        bench_ret = _period_returns(result.benchmark_equity_curve)
        alpha, beta = _alpha_beta(returns, bench_ret, risk_free_rate=risk_free_rate)
        metrics["alpha"] = alpha
        metrics["beta"] = beta
        if result.benchmark_equity_curve[0].equity > 0:
            b_init = result.benchmark_equity_curve[0].equity
            b_final = result.benchmark_equity_curve[-1].equity
            metrics["benchmark_return_pct"] = (b_final - b_init) / b_init * 100

    return metrics


def _total_return_pct(result: BacktestResult) -> float:
    if result.initial_capital <= 0:
        return 0.0
    return (result.final_equity - result.initial_capital) / result.initial_capital * 100


def _cagr_pct(initial: float, final: float, years: float) -> float:
    if initial <= 0 or final <= 0 or years <= 0:
        return 0.0
    return (math.pow(final / initial, 1.0 / years) - 1.0) * 100


def _annualized_volatility_pct(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    daily_std = math.sqrt(variance)
    return daily_std * math.sqrt(TRADING_DAYS_PER_YEAR) * 100


def _max_drawdown_stats(equity_curve: List[EquityPoint]) -> tuple[float, int]:
    if not equity_curve:
        return 0.0, 0
    peak = equity_curve[0].equity
    max_dd = 0.0
    max_duration = 0
    current_duration = 0

    for point in equity_curve:
        if point.equity >= peak:
            peak = point.equity
            current_duration = 0
        else:
            current_duration += 1
            max_duration = max(max_duration, current_duration)
            if peak > 0:
                dd = (peak - point.equity) / peak
                max_dd = max(max_dd, dd)

    return max_dd * 100, max_duration


def _period_returns(equity_curve: List[EquityPoint]) -> List[float]:
    returns: List[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        curr = equity_curve[i].equity
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _sharpe_ratio(equity_curve: List[EquityPoint], risk_free_rate: float = 0.0) -> float:
    """Annualized Sharpe ratio computed from daily equity returns."""
    if len(equity_curve) < 3:
        return 0.0

    returns = _period_returns(equity_curve)
    if len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0.0

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    daily_sharpe = (mean_return - daily_rf) / std_dev
    return daily_sharpe * math.sqrt(TRADING_DAYS_PER_YEAR)


def _sortino_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    """Annualized Sortino ratio using downside semi-deviation."""
    if len(returns) < 2:
        return 0.0

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    mean_return = sum(returns) / len(returns)
    downside_diffs = [min(0.0, r - daily_rf) for r in returns]
    downside_variance = sum(d**2 for d in downside_diffs) / len(returns)
    downside_dev = math.sqrt(downside_variance)

    if downside_dev == 0:
        return 0.0 if mean_return <= daily_rf else math.inf

    return ((mean_return - daily_rf) / downside_dev) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _omega_ratio(returns: List[float], threshold: float = 0.0) -> float:
    """Omega ratio: probability-weighted ratio of gains vs losses."""
    if not returns:
        return 0.0
    gains = sum(max(0.0, r - threshold) for r in returns)
    losses = sum(max(0.0, threshold - r) for r in returns)
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return gains / losses


def _value_at_risk(returns: List[float], confidence: float = 0.95) -> tuple[float, float]:
    """Historical Value at Risk (VaR) and Conditional VaR (CVaR / Expected Shortfall) in %."""
    if len(returns) < 10:
        return 0.0, 0.0
    sorted_ret = sorted(returns)
    cutoff_count = max(1, int(round((1.0 - confidence) * len(sorted_ret))))
    tail = sorted_ret[:cutoff_count]
    var_daily = abs(tail[-1]) if tail[-1] < 0 else 0.0
    cvar_daily = abs(sum(tail) / len(tail)) if (sum(tail) / len(tail)) < 0 else 0.0
    return var_daily * 100, cvar_daily * 100


def _alpha_beta(
    strat_returns: List[float], bench_returns: List[float], risk_free_rate: float = 0.0
) -> tuple[float, float]:
    """Calculate annualized Alpha and Beta relative to benchmark."""
    n = min(len(strat_returns), len(bench_returns))
    if n < 5:
        return 0.0, 1.0

    sr = strat_returns[:n]
    br = bench_returns[:n]
    mean_s = sum(sr) / n
    mean_b = sum(br) / n

    cov = sum((sr[i] - mean_s) * (br[i] - mean_b) for i in range(n)) / (n - 1)
    var_b = sum((br[i] - mean_b) ** 2 for i in range(n)) / (n - 1)

    if var_b == 0:
        return 0.0, 1.0

    beta = cov / var_b
    annual_s = mean_s * TRADING_DAYS_PER_YEAR
    annual_b = mean_b * TRADING_DAYS_PER_YEAR
    alpha = annual_s - (risk_free_rate + beta * (annual_b - risk_free_rate))
    return alpha * 100, beta


def _skewness(values: List[float], mean: float, std: float) -> float:
    n = len(values)
    if std == 0 or n == 0:
        return 0.0
    return sum((v - mean) ** 3 for v in values) / n / std**3


def _pearson_kurtosis(values: List[float], mean: float, std: float) -> float:
    """Raw (non-excess) kurtosis - a normal distribution scores 3.0."""
    n = len(values)
    if std == 0 or n == 0:
        return 3.0
    return sum((v - mean) ** 4 for v in values) / n / std**4


def probabilistic_sharpe_ratio(
    equity_curve: List[EquityPoint],
    benchmark_sharpe: float = 0.0,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Probabilistic Sharpe Ratio (PSR) (Bailey & Lopez de Prado, 2012).
    Calculates the probability (0 to 1) that the estimated Sharpe Ratio is
    strictly greater than a benchmark Sharpe Ratio (default 0.0).
    """
    returns = _period_returns(equity_curve)
    t = len(returns)
    if t < 3:
        return 0.0

    mean_return = sum(returns) / t
    variance = sum((r - mean_return) ** 2 for r in returns) / (t - 1)
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return 0.0

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    daily_sr = (mean_return - daily_rf) / std_dev
    sr_ann = daily_sr * math.sqrt(TRADING_DAYS_PER_YEAR)

    skew = _skewness(returns, mean_return, std_dev)
    kurt = _pearson_kurtosis(returns, mean_return, std_dev)

    # PSR formula adjusted for non-normality
    denom_sq = 1.0 - skew * daily_sr + (kurt - 1.0) / 4.0 * daily_sr**2
    denom = math.sqrt(max(1e-12, denom_sq))
    z = (daily_sr - (benchmark_sharpe / math.sqrt(TRADING_DAYS_PER_YEAR))) * math.sqrt(t - 1) / denom
    return NormalDist().cdf(z)


def deflated_sharpe_ratio(
    equity_curve: List[EquityPoint],
    num_trials: int,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).
    Corrects for selection bias, multiple testing, and non-normality.
    """
    if num_trials < 2:
        raise ValueError(
            "num_trials must be at least 2 - the DSR corrects for a search "
            "over multiple trials, so it needs to know how many were tried"
        )

    returns = _period_returns(equity_curve)
    t = len(returns)
    if t < 3:
        return 0.0

    mean_return = sum(returns) / t
    variance = sum((r - mean_return) ** 2 for r in returns) / (t - 1)
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return 0.0

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    sr_hat = (mean_return - daily_rf) / std_dev
    skew = _skewness(returns, mean_return, std_dev)
    kurt = _pearson_kurtosis(returns, mean_return, std_dev)

    variance_term = 1 - skew * sr_hat + (kurt - 1) / 4 * sr_hat**2
    variance_term = max(variance_term, 1e-12)

    sigma_sr = math.sqrt(variance_term / (t - 1))

    normal = NormalDist()
    z1 = normal.inv_cdf(1 - 1 / num_trials)
    z2 = normal.inv_cdf(1 - 1 / (num_trials * math.e))
    sr_expected_max = sigma_sr * ((1 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)

    numerator = (sr_hat - sr_expected_max) * math.sqrt(t - 1)
    denominator = math.sqrt(variance_term)
    return normal.cdf(numerator / denominator)
