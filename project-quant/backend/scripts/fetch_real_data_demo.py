"""
Demo: pull REAL, legal stock data (via yfinance -> Yahoo Finance) and run
it through the same domain engine used in demo.py.

This file is intentionally OUTSIDE app/domain/ - fetching data from an
external source is an infrastructure concern, not a domain concern. In
week 2/3 this logic will move into app/infrastructure/market_data.py
behind a clean interface the domain layer never has to know about.

Run with: python scripts/fetch_real_data_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain import (
    BacktestEngine,
    FibonacciRetracementStrategy,
    SmaCrossoverStrategy,
    compute_metrics,
    find_swing_range,
    fibonacci_retracement_levels,
    standard_pivot_points,
)
from app.domain.models import Bar


def fetch_bars(ticker: str, period: str = "6mo") -> list[Bar]:
    """Fetch OHLC data from Yahoo Finance via yfinance and convert to Bar objects."""
    import yfinance as yf

    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
    if df.empty:
        raise RuntimeError(f"No data returned for {ticker}")

    # yfinance sometimes returns MultiIndex columns for a single ticker.
    if hasattr(df.columns, "get_level_values"):
        df.columns = df.columns.get_level_values(0)

    bars = []
    for ts, row in df.iterrows():
        bars.append(
            Bar(
                date=ts.date(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
            )
        )
    return bars


def main():
    ticker = "AAPL"
    print(f"Fetching {ticker} from Yahoo Finance (legal, no scraping, official public API)...")
    bars = fetch_bars(ticker)
    print(f"Got {len(bars)} bars: {bars[0].date} -> {bars[-1].date}\n")

    # -- Fibonacci retracement snapshot on the most recent swing --
    swing = find_swing_range(bars, lookback=30)
    levels = fibonacci_retracement_levels(swing, uptrend=True)
    print("Fibonacci retracement (last 30 bars):")
    for ratio, price in levels.items():
        print(f"  {ratio:>5.1%}: {price:,.2f}")

    pivots = standard_pivot_points(bars[-1])
    print(f"\nNext-session pivot points: pivot={pivots.pivot:,.2f} "
          f"R1={pivots.r1:,.2f} S1={pivots.s1:,.2f}\n")

    # -- Run both strategies through the SAME domain engine --
    for name, strategy in [
        ("SMA crossover (5/20)", SmaCrossoverStrategy(fast_period=5, slow_period=20)),
        ("Fibonacci retracement", FibonacciRetracementStrategy(lookback=30)),
    ]:
        engine = BacktestEngine(initial_capital=10_000)
        result = engine.run(bars, strategy)
        metrics = compute_metrics(result)
        print(f"--- {name} ---")
        print(f"  trades={metrics['num_trades']:.0f}  "
              f"return={metrics['total_return_pct']:.2f}%  "
              f"sharpe={metrics['sharpe_ratio']:.2f}  "
              f"max_dd={metrics['max_drawdown_pct']:.2f}%")


if __name__ == "__main__":
    main()
