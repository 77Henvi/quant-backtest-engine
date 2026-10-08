from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domain.models import Bar
from app.infrastructure.db import get_db
from app.infrastructure.models import BacktestJobORM
from app.infrastructure.repository import (
    get_backtest_job,
    list_backtest_jobs,
    save_backtest_job,
    save_failed_job,
)
from app.services.backtest_service import available_strategies, run_backtest

from ..schemas import BacktestRequest, BacktestResponse, TradeOut

router = APIRouter(prefix="/backtests", tags=["backtests"])


def _to_response(job: BacktestJobORM) -> BacktestResponse:
    return BacktestResponse(
        id=job.id,
        status=job.status,
        strategy=job.strategy_name,
        params=job.strategy_params,
        initial_capital=job.initial_capital,
        position_fraction=job.position_fraction,
        final_equity=job.final_equity,
        metrics=job.metrics,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        trades=[
            TradeOut(
                entry_date=t.entry_date,
                entry_price=t.entry_price,
                quantity=t.quantity,
                exit_date=t.exit_date,
                exit_price=t.exit_price,
                pnl=t.pnl,
                return_pct=t.return_pct,
            )
            for t in job.trades
        ],
    )


@router.get("/strategies", response_model=List[str])
def list_strategies():
    """Which strategy names are valid for the `strategy` field below."""
    return available_strategies()


@router.post("", response_model=BacktestResponse, status_code=201)
def create_backtest(payload: BacktestRequest, db: Session = Depends(get_db)):
    try:
        bars = [
            Bar(date=b.date, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)
            for b in payload.bars
        ]
        result, metrics = run_backtest(
            bars=bars,
            strategy_name=payload.strategy,
            strategy_params=payload.params,
            initial_capital=payload.initial_capital,
            position_fraction=payload.position_fraction,
            commission_rate=payload.commission_rate,
            slippage_rate=payload.slippage_rate,
            num_trials=payload.num_trials,
            risk_free_rate=payload.risk_free_rate,
        )
    except ValueError as exc:
        # Bad strategy name / bad params / bad bar data -> the caller's
        # fault, not a server error. Still record the failed attempt so
        # it's visible in GET /backtests for debugging.
        job = save_failed_job(
            db,
            strategy_name=payload.strategy,
            strategy_params=payload.params,
            initial_capital=payload.initial_capital,
            position_fraction=payload.position_fraction,
            error_message=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = save_backtest_job(
        db,
        strategy_name=payload.strategy,
        strategy_params=payload.params,
        initial_capital=payload.initial_capital,
        position_fraction=payload.position_fraction,
        result=result,
        metrics=metrics,
    )
    return _to_response(job)


@router.get("/{job_id}", response_model=BacktestResponse)
def get_backtest(job_id: str, db: Session = Depends(get_db)):
    job = get_backtest_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No backtest job with id '{job_id}'")
    return _to_response(job)


@router.get("", response_model=List[BacktestResponse])
def list_backtests(limit: int = 20, db: Session = Depends(get_db)):
    jobs = list_backtest_jobs(db, limit=limit)
    return [_to_response(job) for job in jobs]
