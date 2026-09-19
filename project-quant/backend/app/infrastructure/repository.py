"""
Repository: the ONLY place that translates between domain objects
(app.domain.models) and database rows (app.infrastructure.models).

Why bother? Because the API layer and the services layer should never
import SQLAlchemy directly. If we ever swap Postgres for something
else, this is the one file that changes.
"""

import math
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.domain.models import BacktestResult

from .models import BacktestJobORM, TradeORM


def _json_safe_metrics(metrics: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Replace inf/-inf/nan with None before this dict is persisted.

    Domain metrics like profit_factor can be legitimately infinite (a
    backtest with wins and zero losing trades). That's mathematically
    correct and the domain layer should keep reporting it honestly.
    But standard JSON has no representation for Infinity/NaN - SQLite's
    JSON column doesn't validate this and silently stores an invalid
    literal, while Postgres's JSONB column correctly REJECTS it at
    INSERT time, raising an unhandled 500. This sanitization step
    belongs here (the persistence boundary), not in the domain, because
    "JSON must be finite" is a storage concern, not a math concern.
    """
    return {
        key: (None if isinstance(value, float) and not math.isfinite(value) else value)
        for key, value in metrics.items()
    }


def save_backtest_job(
    db: Session,
    strategy_name: str,
    strategy_params: dict,
    initial_capital: float,
    position_fraction: float,
    result: BacktestResult,
    metrics: dict,
) -> BacktestJobORM:
    job = BacktestJobORM(
        strategy_name=strategy_name,
        strategy_params=strategy_params,
        initial_capital=initial_capital,
        position_fraction=position_fraction,
        status="completed",
        final_equity=result.final_equity,
        metrics=_json_safe_metrics(metrics),
    )
    for trade in result.trades:
        job.trades.append(
            TradeORM(
                entry_date=trade.entry_date.isoformat(),
                entry_price=trade.entry_price,
                quantity=trade.quantity,
                exit_date=trade.exit_date.isoformat() if trade.exit_date else None,
                exit_price=trade.exit_price,
                pnl=trade.pnl,
                return_pct=trade.return_pct,
            )
        )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def save_failed_job(
    db: Session, strategy_name: str, strategy_params: dict, initial_capital: float,
    position_fraction: float, error_message: str,
) -> BacktestJobORM:
    job = BacktestJobORM(
        strategy_name=strategy_name,
        strategy_params=strategy_params,
        initial_capital=initial_capital,
        position_fraction=position_fraction,
        status="failed",
        error_message=error_message,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_backtest_job(db: Session, job_id: str) -> Optional[BacktestJobORM]:
    return db.get(BacktestJobORM, job_id)


def list_backtest_jobs(db: Session, limit: int = 20) -> List[BacktestJobORM]:
    return (
        db.query(BacktestJobORM)
        .order_by(BacktestJobORM.created_at.desc())
        .limit(limit)
        .all()
    )
