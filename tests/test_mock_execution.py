"""Tests for the execution interface, MockExecutionHandler, and factory (Module 6).

Covers: the abstract contract, order fill / position tracking / close+P&L,
spread/slippage applied against the trader, SL/TP bar-by-bar exits, and the
config-driven mock<->real factory (without ever importing MetaTrader5).
"""
from __future__ import annotations

import pytest

from src.execution.base import ExecutionHandler
from src.execution.factory import get_execution_handler
from src.execution.mock import MockExecutionHandler


@pytest.fixture
def h():
    handler = MockExecutionHandler()
    handler.connect()
    return handler


# --------------------------------------------------------------------------- #
# Interface / contract
# --------------------------------------------------------------------------- #
def test_mock_is_execution_handler(h):
    assert isinstance(h, ExecutionHandler)


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        ExecutionHandler()  # abstract


def test_order_before_connect_raises():
    handler = MockExecutionHandler()  # not connected
    with pytest.raises(RuntimeError, match="Not connected"):
        handler.place_order("EURUSD", "BUY", 1.0, 1.0, 1.1, price=1.05)


# --------------------------------------------------------------------------- #
# Orders + position tracking
# --------------------------------------------------------------------------- #
def test_place_order_fills_and_tracks(h):
    res = h.place_order("EURUSD", "BUY", 1000, sl=1.09, tp=1.12, price=1.10)
    assert res["status"] == "filled"
    assert res["ticket"] == 1
    assert res["price"] == 1.10  # no spread/slippage by default
    assert len(h.get_open_positions()) == 1


def test_tickets_are_unique(h):
    a = h.place_order("EURUSD", "BUY", 1, 1.0, 1.2, price=1.10)
    b = h.place_order("EURUSD", "SELL", 1, 1.2, 1.0, price=1.10)
    assert a["ticket"] != b["ticket"]
    assert len(h.get_open_positions()) == 2


def test_invalid_side_raises(h):
    with pytest.raises(ValueError):
        h.place_order("EURUSD", "HOLD", 1, 1.0, 1.2, price=1.10)


def test_missing_price_raises(h):
    with pytest.raises(ValueError, match="fill price"):
        h.place_order("EURUSD", "BUY", 1, 1.0, 1.2)


# --------------------------------------------------------------------------- #
# Spread / slippage applied against the trader
# --------------------------------------------------------------------------- #
def test_spread_slippage_worsens_buy_fill():
    h = MockExecutionHandler(spread=0.0001, slippage=0.0001)
    h.connect()
    res = h.place_order("EURUSD", "BUY", 1, 1.0, 1.2, price=1.10)
    # BUY fills HIGHER by spread+slippage
    assert res["price"] == pytest.approx(1.10 + 0.0002)


def test_spread_slippage_worsens_sell_fill():
    h = MockExecutionHandler(spread=0.0001, slippage=0.0001)
    h.connect()
    res = h.place_order("EURUSD", "SELL", 1, 1.2, 1.0, price=1.10)
    # SELL fills LOWER by spread+slippage
    assert res["price"] == pytest.approx(1.10 - 0.0002)


# --------------------------------------------------------------------------- #
# Closing + P&L
# --------------------------------------------------------------------------- #
def test_close_buy_profit(h):
    h.place_order("EURUSD", "BUY", 1000, 1.09, 1.12, price=1.10)
    res = h.close_position(1, price=1.11)
    assert res["status"] == "closed"
    # +0.01 * 1000 = +10
    assert res["pnl"] == pytest.approx(10.0)
    assert h.get_open_positions() == []


def test_close_sell_profit(h):
    h.place_order("EURUSD", "SELL", 1000, 1.11, 1.08, price=1.10)
    res = h.close_position(1, price=1.09)
    # SELL profits when price falls: (1.10 - 1.09)*1000 = +10
    assert res["pnl"] == pytest.approx(10.0)


def test_close_unknown_ticket(h):
    res = h.close_position(999)
    assert res["status"] == "not_found"


def test_closed_trades_recorded(h):
    h.place_order("EURUSD", "BUY", 1, 1.0, 1.2, price=1.10)
    h.close_position(1, price=1.11)
    assert len(h.closed_trades) == 1


# --------------------------------------------------------------------------- #
# SL / TP bar-by-bar exits (backtester driver)
# --------------------------------------------------------------------------- #
def test_buy_take_profit_triggers(h):
    h.place_order("EURUSD", "BUY", 1000, sl=1.09, tp=1.12, price=1.10)
    fired = h.check_sl_tp("EURUSD", high=1.13, low=1.10)  # high reached TP
    assert len(fired) == 1
    assert fired[0]["exit_reason"] == "take_profit"
    assert fired[0]["exit_price"] == 1.12


def test_buy_stop_loss_triggers(h):
    h.place_order("EURUSD", "BUY", 1000, sl=1.09, tp=1.12, price=1.10)
    fired = h.check_sl_tp("EURUSD", high=1.10, low=1.08)  # low reached SL
    assert len(fired) == 1
    assert fired[0]["exit_reason"] == "stop_loss"
    assert fired[0]["exit_price"] == 1.09


def test_sell_stop_loss_triggers(h):
    h.place_order("EURUSD", "SELL", 1000, sl=1.11, tp=1.08, price=1.10)
    fired = h.check_sl_tp("EURUSD", high=1.12, low=1.10)  # high reached SL
    assert len(fired) == 1
    assert fired[0]["exit_reason"] == "stop_loss"


def test_both_touched_assumes_stop_first(h):
    # Bar spans both SL and TP -> conservative: stop hit first.
    h.place_order("EURUSD", "BUY", 1000, sl=1.09, tp=1.12, price=1.10)
    fired = h.check_sl_tp("EURUSD", high=1.13, low=1.08)
    assert fired[0]["exit_reason"] == "stop_loss"


def test_no_trigger_leaves_position_open(h):
    h.place_order("EURUSD", "BUY", 1000, sl=1.09, tp=1.12, price=1.10)
    fired = h.check_sl_tp("EURUSD", high=1.11, low=1.095)
    assert fired == []
    assert len(h.get_open_positions()) == 1


# --------------------------------------------------------------------------- #
# Factory (config-driven swap)
# --------------------------------------------------------------------------- #
def test_factory_returns_mock_by_default():
    handler = get_execution_handler("mock")
    assert isinstance(handler, MockExecutionHandler)
    assert isinstance(handler, ExecutionHandler)


def test_factory_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown execution handler"):
        get_execution_handler("bogus")


def test_factory_does_not_import_metatrader5():
    """Selecting mock must not pull in MetaTrader5 (keeps macOS runnable)."""
    import sys
    get_execution_handler("mock")
    assert "MetaTrader5" not in sys.modules


def test_factory_forwards_kwargs():
    handler = get_execution_handler("mock", spread=0.0005)
    assert handler.spread == 0.0005
