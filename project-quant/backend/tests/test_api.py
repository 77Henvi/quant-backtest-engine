"""
API-level tests.

Uses an isolated in-memory SQLite database per test session (overriding
the get_db dependency) so these tests never touch a real Postgres and
never leave a quant.db file behind. This is the standard FastAPI
pattern for testing routes without a live database server.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.db import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture()
def client():
    # StaticPool keeps a single shared connection alive so every session
    # in this test sees the same in-memory database (by default each
    # new SQLite connection gets its own throwaway :memory: database).
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_bars(closes):
    return [
        {
            "date": f"2024-01-{i + 1:02d}",
            "open": c,
            "high": c + 0.5,
            "low": c - 0.5,
            "close": c,
            "volume": 1000,
        }
        for i, c in enumerate(closes)
    ]


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestListStrategies:
    def test_returns_known_strategies(self, client):
        response = client.get("/backtests/strategies")
        assert response.status_code == 200
        names = response.json()
        assert "sma_crossover" in names
        assert "fibonacci_retracement" in names


class TestCreateBacktest:
    def test_successful_backtest_returns_201(self, client):
        payload = {
            "bars": make_bars([100, 101, 99, 105, 110, 108, 112, 115, 111, 120]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 2, "slow_period": 4},
            "initial_capital": 10000,
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "completed"
        assert body["strategy"] == "sma_crossover"
        assert "id" in body
        assert body["metrics"] is not None
        assert body["final_equity"] is not None
        assert "deflated_sharpe_ratio" not in body["metrics"]

    def test_num_trials_adds_deflated_sharpe_ratio(self, client):
        payload = {
            "bars": make_bars([100, 101, 99, 105, 110, 108, 112, 115, 111, 120, 118, 125, 130]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 2, "slow_period": 4},
            "num_trials": 50,
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 201
        metrics = response.json()["metrics"]
        assert "deflated_sharpe_ratio" in metrics
        assert 0.0 <= metrics["deflated_sharpe_ratio"] <= 1.0

    def test_num_trials_below_two_is_rejected_by_schema(self, client):
        payload = {
            "bars": make_bars([100, 101, 102, 103]),
            "strategy": "sma_crossover",
            "params": {},
            "num_trials": 1,  # DSR needs a real search of >= 2 trials
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 422

    def test_infinite_profit_factor_does_not_crash_the_response(self, client):
        """Regression test: a backtest with wins and zero losing trades
        produces profit_factor = math.inf, which is mathematically
        correct but not valid JSON. This must come back as `null` in the
        response - not crash with a 500 (as it did when persisted to a
        real Postgres JSONB column, which rejects the literal Infinity
        that SQLite silently tolerates)."""
        payload = {
            "bars": make_bars([100, 102, 105, 101, 99, 95, 94, 98, 103, 108, 110, 105]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 2, "slow_period": 4},
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 201
        metrics = response.json()["metrics"]
        assert metrics["num_trades"] == 1
        assert metrics["profit_factor"] is None
        # The raw bytes must be strict, parseable JSON - no bare
        # "Infinity"/"NaN" tokens that a strict JSON parser would reject.
        assert b"Infinity" not in response.content
        assert b"NaN" not in response.content

    def test_unknown_strategy_returns_422(self, client):
        payload = {
            "bars": make_bars([100, 101, 102]),
            "strategy": "does_not_exist",
            "params": {},
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 422
        assert "does_not_exist" in response.json()["detail"]

    def test_invalid_strategy_params_returns_422(self, client):
        payload = {
            "bars": make_bars([100, 101, 102, 103, 104]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 20, "slow_period": 5},  # invalid: fast >= slow
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 422

    def test_too_few_bars_returns_422_from_pydantic(self, client):
        payload = {
            "bars": make_bars([100]),  # min_length=2 on the schema
            "strategy": "sma_crossover",
            "params": {},
        }
        response = client.post("/backtests", json=payload)
        assert response.status_code == 422

    def test_inconsistent_bar_ohlc_returns_422_not_500(self, client):
        """Regression test: a Bar failing domain validation (e.g. open
        outside the high/low range) must surface as a client error, not
        an unhandled 500."""
        bars = make_bars([100, 101, 102])
        bars[1]["open"] = 999  # way outside this bar's high/low
        payload = {"bars": bars, "strategy": "sma_crossover", "params": {}}
        response = client.post("/backtests", json=payload)
        assert response.status_code == 422

    def test_unsorted_bars_rejected(self, client):
        bars = make_bars([100, 101, 102])
        bars[0], bars[1] = bars[1], bars[0]  # break the ordering
        payload = {"bars": bars, "strategy": "sma_crossover", "params": {}}
        response = client.post("/backtests", json=payload)
        assert response.status_code == 422


class TestGetBacktest:
    def test_get_existing_job(self, client):
        create_payload = {
            "bars": make_bars([100, 102, 101, 105, 108]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 2, "slow_period": 3},
        }
        created = client.post("/backtests", json=create_payload).json()

        response = client.get(f"/backtests/{created['id']}")
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_get_missing_job_returns_404(self, client):
        response = client.get("/backtests/does-not-exist")
        assert response.status_code == 404


class TestListBacktests:
    def test_list_returns_created_jobs(self, client):
        payload = {
            "bars": make_bars([100, 102, 101, 105, 108]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 2, "slow_period": 3},
        }
        client.post("/backtests", json=payload)
        client.post("/backtests", json=payload)

        response = client.get("/backtests")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_respects_limit(self, client):
        payload = {
            "bars": make_bars([100, 102, 101, 105, 108]),
            "strategy": "sma_crossover",
            "params": {"fast_period": 2, "slow_period": 3},
        }
        for _ in range(3):
            client.post("/backtests", json=payload)

        response = client.get("/backtests?limit=1")
        assert len(response.json()) == 1
