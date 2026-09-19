from fastapi import FastAPI

from app.api.routes import backtests
from app.core.config import settings
from app.infrastructure.db import Base, engine

# Week 2 keeps this simple: create tables on startup if they don't exist.
# Week 3+ swaps this for proper Alembic migrations once the schema needs
# to evolve without dropping data.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="Backtest engine API for Project Quant",
    version="0.2.0",
)

app.include_router(backtests.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
