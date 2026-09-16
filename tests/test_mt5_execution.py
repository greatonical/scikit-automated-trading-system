"""Tests for MT5ExecutionHandler (Module 8).

MetaTrader5 is Windows-only and cannot install on macOS, so we inject a FAKE
`MetaTrader5` module into sys.modules to verify the handler maps the MT5 API onto
our ExecutionHandler contract correctly. The key macOS-safety test confirms the
module imports without MetaTrader5 present (lazy import).

Volume contract: the engine speaks UNITS of base currency; MT5 speaks LOTS. The
handler converts with the broker's symbol_info, rounding down (never enlarging).
"""
from __future__ import annotations

import sys
import types

import pytest

from src.execution.base import ExecutionHandler
from src.execution.mt5 import MT5ExecutionHandler
from src.risk_manager import RiskManager


# --------------------------------------------------------------------------- #
# A fake MetaTrader5 module
# --------------------------------------------------------------------------- #
def _fake_mt5():
    m = types.ModuleType("MetaTrader5")
    # constants
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.POSITION_TYPE_BUY = 0
    m.POSITION_TYPE_SELL = 1
    m.TRADE_ACTION_DEAL = 1
    m.ORDER_TIME_GTC = 0
    m.ORDER_FILLING_IOC = 1
    m.TRADE_RETCODE_DONE = 10009

    state = {"logged_in": False, "shutdown": False, "requests": [], "tick": True}
    m._state = state

    def initialize():
        return True

    def login(login, password, server):
        state["logged_in"] = True
        return True

    def shutdown():
        state["shutdown"] = True

    def last_error():
        return (0, "ok")

    def symbol_info_tick(symbol):
        if not state["tick"]:
            return None
        return types.SimpleNamespace(ask=1.1002, bid=1.1000)

    def symbol_info(symbol):
        # A standard FX contract: 1 lot = 100,000 units, 0.01-lot steps.
        return types.SimpleNamespace(
            trade_contract_size=100_000.0, volume_step=0.01,
            volume_min=0.01, volume_max=50.0,
        )

    def order_send(request):
        state["requests"].append(request)
        return types.SimpleNamespace(
            retcode=m.TRADE_RETCODE_DONE, order=555, price=request["price"]
        )

    def positions_get(ticket=None):
        pos = types.SimpleNamespace(
            ticket=555, symbol="EURUSD", type=m.POSITION_TYPE_BUY,
            volume=0.1, price_open=1.10, sl=1.09, tp=1.12, profit=5.0,
        )
        if ticket is not None and ticket != 555:
            return ()
        return (pos,)

    m.initialize = initialize
    m.login = login
    m.shutdown = shutdown
    m.last_error = last_error
    m.symbol_info_tick = symbol_info_tick
    m.symbol_info = symbol_info
    m.order_send = order_send
    m.positions_get = positions_get
    return m


@pytest.fixture
def connected_handler(monkeypatch):
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_mt5())
    h = MT5ExecutionHandler(login="5012345678", password="x", server="Demo")
    h.connect()
    return h


# --------------------------------------------------------------------------- #
# macOS safety: import + interface
# --------------------------------------------------------------------------- #
def test_is_execution_handler():
    h = MT5ExecutionHandler(login="1", password="2", server="3")
    assert isinstance(h, ExecutionHandler)


def test_module_imports_without_metatrader5():
    """Importing the module on macOS (no MetaTrader5) must NOT raise."""
    # Already imported at top of file without error — assert it's usable.
    assert MT5ExecutionHandler is not None


def test_connect_without_metatrader5_raises_clear_error(monkeypatch):
    # Ensure MetaTrader5 is absent, then connect() should give a helpful error.
    monkeypatch.setitem(sys.modules, "MetaTrader5", None)
    h = MT5ExecutionHandler(login="1", password="2", server="3")
    with pytest.raises(RuntimeError, match="runs only inside"):
        h.connect()


def test_operations_before_connect_raise():
    h = MT5ExecutionHandler(login="1", password="2", server="3")
    with pytest.raises(RuntimeError, match="Not connected"):
        h.get_open_positions()


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #
def test_connect_logs_in(connected_handler):
    assert connected_handler.connected is True
    assert connected_handler._mt5._state["logged_in"] is True


def test_connect_missing_credentials_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_mt5())
    # Force settings empty too, so the handler's fallback can't pick up real
    # credentials from a populated .env on the dev machine.
    from config import settings
    monkeypatch.setattr(settings, "MT5_LOGIN", "")
    monkeypatch.setattr(settings, "MT5_PASSWORD", "")
    monkeypatch.setattr(settings, "MT5_SERVER", "")
    h = MT5ExecutionHandler(login="", password="", server="")
    with pytest.raises(RuntimeError, match="Missing MT5 demo credentials"):
        h.connect()


def test_disconnect_calls_shutdown(connected_handler):
    connected_handler.disconnect()
    assert connected_handler.connected is False
    assert connected_handler._mt5._state["shutdown"] is True


# --------------------------------------------------------------------------- #
# Orders map onto the interface contract
# --------------------------------------------------------------------------- #
def test_place_buy_order_filled(connected_handler):
    res = connected_handler.place_order("EURUSD", "BUY", 10_000, sl=1.09, tp=1.12)
    assert res["status"] == "filled"
    assert res["ticket"] == 555
    assert res["side"] == "BUY"
    # BUY fills at ask
    assert res["price"] == pytest.approx(1.1002)
    # 10,000 units = 0.1 lot on a 100k contract; returned volume stays in units
    assert res["lots"] == pytest.approx(0.1)
    assert res["volume"] == pytest.approx(10_000)
    assert connected_handler._mt5._state["requests"][-1]["volume"] == pytest.approx(0.1)


def test_place_sell_order_filled(connected_handler):
    res = connected_handler.place_order("EURUSD", "SELL", 10_000, sl=1.11, tp=1.08)
    assert res["status"] == "filled"
    assert res["price"] == pytest.approx(1.1000)  # SELL fills at bid


def test_place_invalid_side_raises(connected_handler):
    with pytest.raises(ValueError):
        connected_handler.place_order("EURUSD", "HOLD", 10_000, 1.0, 1.2)


def test_units_round_down_to_lot_step(connected_handler):
    # 12,345 units = 0.12345 lot -> rounded DOWN to 0.12 (never enlarged).
    res = connected_handler.place_order("EURUSD", "BUY", 12_345, sl=1.09, tp=1.12)
    assert connected_handler._mt5._state["requests"][-1]["volume"] == pytest.approx(0.12)
    assert res["volume"] == pytest.approx(12_000)


def test_below_min_lot_is_rejected_not_enlarged(connected_handler):
    # 500 units = 0.005 lot < 0.01 minimum -> reject; no order reaches MT5.
    res = connected_handler.place_order("EURUSD", "BUY", 500, sl=1.09, tp=1.12)
    assert res["status"] == "rejected"
    assert res["reason"] == "below_min_volume"
    assert connected_handler._mt5._state["requests"] == []


def test_above_max_lot_is_clamped(connected_handler):
    connected_handler.place_order("EURUSD", "BUY", 10_000_000, sl=1.09, tp=1.12)
    assert connected_handler._mt5._state["requests"][-1]["volume"] == pytest.approx(50.0)


def test_riskmanager_plan_becomes_sane_lot_size(connected_handler):
    """A RiskManager plan (units) must reach MT5 as a sane lot size, not as lots.

    1% of $10k risked over a 1.2% stop at 1.10 ≈ 7,576 units ≈ 0.07 lot. Sending
    the raw number as lots would have been a ~7,576-lot order.
    """
    rm = RiskManager(starting_equity=10_000, risk_fraction=0.01, stop_loss_pct=0.012)
    plan = rm.size_position("BUY", entry_price=1.10, volume_zscore=0.0)
    assert plan.volume == pytest.approx(100 / (1.10 * 0.012))
    connected_handler.place_order("EURUSD", "BUY", plan.volume,
                                  sl=plan.stop_loss, tp=plan.take_profit)
    assert connected_handler._mt5._state["requests"][-1]["volume"] == pytest.approx(0.07)


def test_get_open_positions_shape(connected_handler):
    positions = connected_handler.get_open_positions()
    assert len(positions) == 1
    p = positions[0]
    assert p["ticket"] == 555
    assert p["side"] == "BUY"
    assert {"symbol", "volume", "price", "sl", "tp"} <= set(p)
    # Broker's 0.1 lot is reported back in engine units.
    assert p["lots"] == pytest.approx(0.1)
    assert p["volume"] == pytest.approx(10_000)


def test_close_position_success(connected_handler):
    res = connected_handler.close_position(555)
    assert res["status"] == "closed"
    assert res["ticket"] == 555
    # Closing sends the broker's own lot volume back.
    assert connected_handler._mt5._state["requests"][-1]["volume"] == pytest.approx(0.1)


def test_close_position_without_tick_fails_cleanly(connected_handler):
    connected_handler._mt5._state["tick"] = False
    res = connected_handler.close_position(555)
    assert res["status"] == "failed"
    assert res["reason"] == "no_tick"


def test_close_unknown_position(connected_handler):
    res = connected_handler.close_position(999)
    assert res["status"] == "not_found"


# --------------------------------------------------------------------------- #
# Factory wiring (without importing real MetaTrader5)
# --------------------------------------------------------------------------- #
def test_factory_builds_mt5_with_fake_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_mt5())
    from src.execution.factory import get_execution_handler
    h = get_execution_handler("mt5", login="1", password="2", server="Demo")
    assert isinstance(h, MT5ExecutionHandler)
