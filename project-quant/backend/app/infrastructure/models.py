"""
SQLAlchemy ORM models.

These are deliberately SEPARATE classes from app.domain.models, even
though some fields overlap (e.g. Trade). The domain Trade is a pure
dataclass used for simulation math; TradeORM is a database row shape.
Conflating them would mean every schema migration risks breaking the
backtest engine, and every engine refactor risks breaking the domain
layer. Keeping them apart costs a bit of mapping code (see
repository.py) in exchange for the two layers never breaking each other.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class BacktestJobORM(Base):
    __tablename__ = "backtest_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_gen_uuid)
    strategy_name: Mapped[str] = mapped_column(String, nullable=False)
    strategy_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    position_fraction: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    final_equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    trades: Mapped[List["TradeORM"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class TradeORM(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("backtest_jobs.id"))

    entry_date: Mapped[str] = mapped_column(String, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    exit_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    return_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    job: Mapped["BacktestJobORM"] = relationship(back_populates="trades")
