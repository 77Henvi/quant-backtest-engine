"""
Quick manual demo - NOT a test. Run with: python demo.py

Shows the full domain pipeline: Bars -> Strategy -> Engine -> Metrics,
with zero API, zero database, zero cloud. This is exactly the contract
the API layer will call in week 2.
"""

import random
from datetime import date, timedelta

from app.domain import BacktestEngine, SmaCrossoverStrategy, compute_metrics
from app.domain.models import Bar


def make_synthetic_bars(n: int = 120, start_price: float = 100.0, seed: int = 42):
    random.seed(seed)
    bars = []
    price = start_price
    start_date = date(2024, 1, 1)
    for i in range(n):
        drift = random.uniform(-2, 2.2)  # slight upward bias
        price = max(1.0, price + drift)
        high = price + random.uniform(0, 1.5)
        low = price - random.uniform(0, 1.5)
        bars.append(
            Bar(date=start_date + timedelta(days=i), open=price, high=high, low=low, close=price)
        )
    return bars


def main():
    bars = make_synthetic_bars()
    strategy = SmaCrossoverStrategy(fast_period=5, slow_period=20)
    engine = BacktestEngine(initial_capital=10_000, position_fraction=1.0)

    result = engine.run(bars, strategy)
    metrics = compute_metrics(result)

    print(f"Bars simulated   : {len(bars)}")
    print(f"Trades executed  : {len(result.trades)}")
    print(f"Initial capital  : {result.initial_capital:,.2f}")
    print(f"Final equity     : {result.final_equity:,.2f}")
    print("-" * 40)
    for key, value in metrics.items():
        print(f"{key:20s}: {value:,.2f}")


if __name__ == "__main__":
    main()
