from datetime import date

import pytest

from app.domain.models import Bar, Trade


class TestBar:
    def test_valid_bar_is_accepted(self):
        bar = Bar(date=date(2024, 1, 1), open=10, high=12, low=9, close=11)
        assert bar.close == 11

    def test_high_below_low_raises(self):
        with pytest.raises(ValueError):
            Bar(date=date(2024, 1, 1), open=10, high=8, low=9, close=8.5)

    def test_close_outside_high_low_raises(self):
        with pytest.raises(ValueError):
            Bar(date=date(2024, 1, 1), open=10, high=12, low=9, close=15)


class TestTrade:
    def test_open_trade_has_zero_pnl_and_return(self):
        trade = Trade(entry_date=date(2024, 1, 1), entry_price=100, quantity=10)
        assert trade.is_open is True
        assert trade.pnl == 0.0
        assert trade.return_pct == 0.0

    def test_closed_winning_trade(self):
        trade = Trade(
            entry_date=date(2024, 1, 1),
            entry_price=100,
            quantity=10,
            exit_date=date(2024, 1, 5),
            exit_price=110,
        )
        assert trade.is_open is False
        assert trade.pnl == 100.0
        assert trade.return_pct == pytest.approx(0.10)

    def test_closed_losing_trade(self):
        trade = Trade(
            entry_date=date(2024, 1, 1),
            entry_price=100,
            quantity=10,
            exit_date=date(2024, 1, 5),
            exit_price=90,
        )
        assert trade.pnl == -100.0
        assert trade.return_pct == pytest.approx(-0.10)
