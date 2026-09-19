"""
Pydantic schemas: the HTTP contract.

A third set of "Bar"/"Trade"-shaped classes, on purpose - same reasoning
as ORM vs domain. This is what changes when the API's public shape
changes (e.g. renaming a JSON field for frontend convenience) without
touching the engine or the database schema.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class BarIn(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class BacktestRequest(BaseModel):
    bars: List[BarIn] = Field(..., min_length=2, description="Price history, oldest first")
    strategy: str = Field(..., description="e.g. 'sma_crossover', 'fibonacci_retracement'")
    params: Dict[str, Any] = Field(default_factory=dict, description="Strategy constructor kwargs")
    initial_capital: float = Field(default=10_000.0, gt=0)
    position_fraction: float = Field(default=1.0, gt=0, le=1.0)
    num_trials: Optional[int] = Field(
        default=None,
        ge=2,
        description=(
            "How many strategy/parameter combinations you tried before this "
            "one. Optional - when provided, the response includes a "
            "deflated_sharpe_ratio metric correcting for that search."
        ),
    )

    @field_validator("bars")
    @classmethod
    def bars_must_be_sorted(cls, bars: List[BarIn]) -> List[BarIn]:
        dates = [b.date for b in bars]
        if dates != sorted(dates):
            raise ValueError("bars must be sorted oldest-to-newest by date")
        return bars


class TradeOut(BaseModel):
    entry_date: str
    entry_price: float
    quantity: float
    exit_date: Optional[str]
    exit_price: Optional[float]
    pnl: float
    return_pct: float


class BacktestResponse(BaseModel):
    id: str
    status: str
    strategy: str
    params: Dict[str, Any]
    initial_capital: float
    position_fraction: float
    final_equity: Optional[float] = None
    metrics: Optional[Dict[str, Optional[float]]] = None
    trades: List[TradeOut] = []
    error_message: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}
