"""
Domain models for the backtest engine.

This module has ZERO dependencies on any framework, database, or cloud
service. It only knows about dataclasses and the standard library.
That is intentional: the domain layer must be testable and reusable
without spinning up a database, an API server, or a cloud emulator.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional


class Signal(Enum):
    """A trading decision emitted by a strategy for a single bar."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Bar:
    """One OHLCV price bar (e.g. one trading day)."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"Bar on {self.date}: high ({self.high}) < low ({self.low})")
        for name, value in (("open", self.open), ("close", self.close)):
            if not (self.low <= value <= self.high):
                raise ValueError(
                    f"Bar on {self.date}: {name} ({value}) is outside [low, high] "
                    f"range ({self.low}, {self.high})"
                )


@dataclass
class Trade:
    """
    A single long position opened and (eventually) closed.

    A trade is "open" while exit_date/exit_price are None. The engine
    is responsible for closing any trade still open at the end of a run.
    """

    entry_date: date
    entry_price: float
    quantity: float
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None

    @property
    def is_open(self) -> bool:
        return self.exit_date is None or self.exit_price is None

    @property
    def pnl(self) -> float:
        """Absolute profit/loss in currency units. 0.0 while still open."""
        if self.is_open:
            return 0.0
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def return_pct(self) -> float:
        """Percentage return of the trade. 0.0 while still open."""
        if self.is_open or self.entry_price == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price


@dataclass(frozen=True)
class EquityPoint:
    """Portfolio value (cash + mark-to-market position) at one point in time."""

    date: date
    equity: float


@dataclass
class BacktestResult:
    """Everything a backtest run produces. Metrics are computed separately."""

    trades: List[Trade]
    equity_curve: List[EquityPoint]
    initial_capital: float
    final_equity: float
