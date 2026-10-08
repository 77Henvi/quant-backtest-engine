"""
Pydantic schemas: the HTTP contract.
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
    strategy: str = Field(..., description="e.g. 'sma_crossover', 'fibonacci_retracement', 'macd_crossover'")
    params: Dict[str, Any] = Field(default_factory=dict, description="Strategy constructor kwargs")
    initial_capital: float = Field(default=10_000.0, gt=0)
    position_fraction: float = Field(default=1.0, gt=0, le=1.0)
    commission_rate: float = Field(default=0.0, ge=0.0, le=0.1, description="Broker commission rate e.g. 0.001 = 0.1%")
    slippage_rate: float = Field(default=0.0, ge=0.0, le=0.05, description="Market execution slippage rate e.g. 0.0005 = 5 bps")
    risk_free_rate: float = Field(default=0.0, ge=0.0, description="Annual risk-free rate e.g. 0.02 = 2%")
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
