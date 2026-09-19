"""
Backtest service: the use-case layer.

This is the ONLY place that knows both "here's how to build a strategy
from a name + params" and "here's how to run it through the engine".
The API layer calls this; this calls the domain layer. The domain layer
never calls back up into this file - dependencies point one way.
"""

from typing import Any, Dict, List, Optional, Tuple, Type

from app.domain import (
    BacktestEngine,
    BacktestResult,
    FibonacciRetracementStrategy,
    RSIMeanReversionStrategy,
    SmaCrossoverStrategy,
    Strategy,
    compute_metrics,
)
from app.domain.models import Bar

# Adding a new strategy to the API is exactly one line here - nothing
# else in app/api or app/services needs to change.
STRATEGY_REGISTRY: Dict[str, Type[Strategy]] = {
    "sma_crossover": SmaCrossoverStrategy,
    "fibonacci_retracement": FibonacciRetracementStrategy,
    "rsi_mean_reversion": RSIMeanReversionStrategy,
}


def available_strategies() -> List[str]:
    return sorted(STRATEGY_REGISTRY.keys())


def build_strategy(name: str, params: Dict[str, Any]) -> Strategy:
    strategy_cls = STRATEGY_REGISTRY.get(name)
    if strategy_cls is None:
        raise ValueError(
            f"Unknown strategy '{name}'. Available strategies: {available_strategies()}"
        )
    try:
        return strategy_cls(**params)
    except TypeError as exc:
        raise ValueError(f"Invalid params for strategy '{name}': {exc}") from exc


def run_backtest(
    bars: List[Bar],
    strategy_name: str,
    strategy_params: Dict[str, Any],
    initial_capital: float,
    position_fraction: float,
    num_trials: Optional[int] = None,
) -> Tuple[BacktestResult, Dict[str, float]]:
    """Build the strategy, run it through the engine, compute metrics.

    Raises ValueError for anything the caller did wrong (unknown
    strategy, bad params, bad engine config) so the API layer can turn
    it into a 422 without needing to know engine internals.

    `num_trials`, when given, adds a deflated_sharpe_ratio metric that
    corrects the Sharpe ratio for how many strategies/parameter
    combinations were searched before this one was picked.
    """
    strategy = build_strategy(strategy_name, strategy_params)
    engine = BacktestEngine(initial_capital=initial_capital, position_fraction=position_fraction)
    result = engine.run(bars, strategy)
    metrics = compute_metrics(result, num_trials=num_trials)
    return result, metrics
