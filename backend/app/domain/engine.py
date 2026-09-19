"""
Backtest engine: the piece that actually simulates trading.

Design choices, spelled out on purpose so future-you (or a reviewer)
doesn't have to reverse-engineer them:

- Long-only, single position at a time (v1). No shorting, no leverage,
  no pyramiding. This keeps the simulation loop auditable; multi-position
  support can be added later behind the same Strategy/Engine interface.
- Fills happen at the CLOSE of the bar that produced the signal. This is
  a simplification (real systems fill at next open) but is deterministic
  and easy to reason about for a first version - documented so nobody
  mistakes this for a bug.
- `position_fraction` controls how much of available cash is deployed
  per trade (1.0 = all-in).
"""

from typing import List, Optional

from .models import Bar, BacktestResult, EquityPoint, Signal, Trade
from .strategy import Strategy


class BacktestEngine:
    def __init__(self, initial_capital: float = 10_000.0, position_fraction: float = 1.0):
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not (0.0 < position_fraction <= 1.0):
            raise ValueError("position_fraction must be in (0, 1]")
        self.initial_capital = initial_capital
        self.position_fraction = position_fraction

    def run(self, bars: List[Bar], strategy: Strategy) -> BacktestResult:
        if not bars:
            return BacktestResult(
                trades=[],
                equity_curve=[],
                initial_capital=self.initial_capital,
                final_equity=self.initial_capital,
            )

        signals = strategy.generate_signals(bars)
        if len(signals) != len(bars):
            raise ValueError(
                f"Strategy must return one signal per bar "
                f"(got {len(signals)} signals for {len(bars)} bars)"
            )

        cash = self.initial_capital
        open_trade: Optional[Trade] = None
        trades: List[Trade] = []
        equity_curve: List[EquityPoint] = []

        for bar, signal in zip(bars, signals):
            if signal is Signal.BUY and open_trade is None:
                allocation = cash * self.position_fraction
                quantity = allocation / bar.close
                open_trade = Trade(entry_date=bar.date, entry_price=bar.close, quantity=quantity)
                cash -= quantity * bar.close

            elif signal is Signal.SELL and open_trade is not None:
                open_trade.exit_date = bar.date
                open_trade.exit_price = bar.close
                cash += open_trade.quantity * bar.close
                trades.append(open_trade)
                open_trade = None

            mark_to_market = open_trade.quantity * bar.close if open_trade else 0.0
            equity_curve.append(EquityPoint(date=bar.date, equity=cash + mark_to_market))

        # Force-close any position still open at the end of the run so
        # results always reflect a fully realized final equity value.
        if open_trade is not None:
            last_bar = bars[-1]
            open_trade.exit_date = last_bar.date
            open_trade.exit_price = last_bar.close
            cash += open_trade.quantity * last_bar.close
            trades.append(open_trade)
            equity_curve[-1] = EquityPoint(date=last_bar.date, equity=cash)

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self.initial_capital,
            final_equity=equity_curve[-1].equity,
        )
