"""Tests for the MT5 RPC boundary (client + server).

Spins up the real RPC server on a random port, but backs it with a FAKE execution
handler so no MetaTrader5 is needed. Verifies the engine's RemoteMT5ExecutionHandler
can drive it over a real socket, that unreachable servers fail gracefully, and that
the optional shared-secret token is enforced.
"""
from __future__ import annotations

import threading
import time

import pytest

from config import settings
from src.execution import mt5_service, rpc_protocol
from src.execution.base import ExecutionHandler
from src.execution.remote_mt5 import RemoteMT5ExecutionHandler


# --------------------------------------------------------------------------- #
# A fake handler injected into the server (stands in for MT5ExecutionHandler)
# --------------------------------------------------------------------------- #
class _FakeHandler(ExecutionHandler):
    def __init__(self):
        self.connected = False
        self.orders = []

    def connect(self):
        self.connected = True
        return True

    def place_order(self, symbol, side, volume, sl, tp, price=None):
        rec = {"ticket": 1, "symbol": symbol, "side": side, "volume": volume,
               "price": price or 1.10, "sl": sl, "tp": tp, "status": "filled"}
        self.orders.append(rec)
        return rec

    def get_open_positions(self):
        return self.orders

    def close_position(self, ticket, price=None):
        return {"ticket": ticket, "status": "closed", "exit_price": price or 1.11}

    def disconnect(self):
        self.connected = False


@pytest.fixture
def rpc_server(monkeypatch):
    """Start the real RPC server class, backed by the fake handler, on a free port."""
    fake = _FakeHandler()
    monkeypatch.setattr(mt5_service, "_handler", fake)
    monkeypatch.setattr(mt5_service, "_get_handler", lambda: fake)
    monkeypatch.setattr(settings, "MT5_RPC_TOKEN", "")  # isolate from any .env token

    server = mt5_service._Server(("127.0.0.1", 0), mt5_service._RPCHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    yield host, port, fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def client(rpc_server):
    host, port, _ = rpc_server
    return RemoteMT5ExecutionHandler(host=host, port=port, timeout=2.0, token="")


# --------------------------------------------------------------------------- #
# Protocol round-trip
# --------------------------------------------------------------------------- #
def test_encode_decode_roundtrip():
    msg = rpc_protocol.make_request("place_order", symbol="EURUSD", volume=0.1)
    assert rpc_protocol.decode(rpc_protocol.encode(msg)) == msg


def test_request_carries_token_only_when_set():
    assert "token" not in rpc_protocol.make_request("ping")
    assert rpc_protocol.make_request("ping", token="")  == {"method": "ping", "args": {}}
    assert rpc_protocol.make_request("ping", token="s3cret")["token"] == "s3cret"


def test_token_check():
    assert rpc_protocol.token_ok({"token": "abc"}, "abc")
    assert not rpc_protocol.token_ok({"token": "abd"}, "abc")
    assert not rpc_protocol.token_ok({}, "abc")
    assert not rpc_protocol.token_ok({"token": "é"}, "abc")  # non-ASCII must not crash


# --------------------------------------------------------------------------- #
# Client drives server over a real socket
# --------------------------------------------------------------------------- #
def test_remote_is_execution_handler(client):
    assert isinstance(client, ExecutionHandler)


def test_ping(client):
    assert client.ping() is True


def test_connect_over_rpc(client):
    assert client.connect() is True


def test_place_order_over_rpc(client, rpc_server):
    _, _, fake = rpc_server
    res = client.place_order("EURUSD", "BUY", 10_000, sl=1.09, tp=1.12, price=1.10)
    assert res["status"] == "filled"
    assert res["symbol"] == "EURUSD"
    # the fake server-side handler actually recorded it
    assert len(fake.orders) == 1


def test_get_positions_over_rpc(client):
    client.place_order("EURUSD", "BUY", 10_000, 1.09, 1.12, price=1.10)
    positions = client.get_open_positions()
    assert isinstance(positions, list)
    assert positions[0]["symbol"] == "EURUSD"


def test_close_position_over_rpc(client):
    res = client.close_position(1, price=1.11)
    assert res["status"] == "closed"


def test_server_reports_unknown_method(client):
    with pytest.raises(RuntimeError, match="unknown method"):
        client._call("does_not_exist")


# --------------------------------------------------------------------------- #
# Shared-secret token (MT5_RPC_TOKEN)
# --------------------------------------------------------------------------- #
def test_server_rejects_missing_token_when_configured(rpc_server, monkeypatch):
    host, port, fake = rpc_server
    monkeypatch.setattr(settings, "MT5_RPC_TOKEN", "s3cret")
    anon = RemoteMT5ExecutionHandler(host=host, port=port, timeout=2.0, token="")
    with pytest.raises(RuntimeError, match="unauthorized"):
        anon.place_order("EURUSD", "BUY", 10_000, 1.09, 1.12, price=1.10)
    assert fake.orders == []          # nothing reached the broker
    assert anon.ping() is False       # even ping is gated


def test_server_rejects_wrong_token(rpc_server, monkeypatch):
    host, port, fake = rpc_server
    monkeypatch.setattr(settings, "MT5_RPC_TOKEN", "s3cret")
    wrong = RemoteMT5ExecutionHandler(host=host, port=port, timeout=2.0, token="nope")
    with pytest.raises(RuntimeError, match="unauthorized"):
        wrong.place_order("EURUSD", "BUY", 10_000, 1.09, 1.12, price=1.10)
    assert fake.orders == []


def test_server_accepts_matching_token(rpc_server, monkeypatch):
    host, port, fake = rpc_server
    monkeypatch.setattr(settings, "MT5_RPC_TOKEN", "s3cret")
    authed = RemoteMT5ExecutionHandler(host=host, port=port, timeout=2.0, token="s3cret")
    assert authed.place_order("EURUSD", "BUY", 10_000, 1.09, 1.12, price=1.10)["status"] == "filled"
    assert len(fake.orders) == 1


def test_client_token_defaults_to_setting(monkeypatch):
    monkeypatch.setattr(settings, "MT5_RPC_TOKEN", "from-env")
    assert RemoteMT5ExecutionHandler(host="127.0.0.1", port=9099).token == "from-env"


def test_server_class_allows_address_reuse_at_bind_time():
    # Must be a class attribute: socketserver reads it inside __init__ when binding.
    assert mt5_service._Server.allow_reuse_address is True


# --------------------------------------------------------------------------- #
# Graceful failure when the server is down
# --------------------------------------------------------------------------- #
def test_unreachable_server_raises_clear_error():
    # Nothing listening on this port.
    client = RemoteMT5ExecutionHandler(host="127.0.0.1", port=1, timeout=0.5)
    with pytest.raises(ConnectionError, match="MT5 service unreachable"):
        client.connect()


def test_ping_false_when_unreachable():
    client = RemoteMT5ExecutionHandler(host="127.0.0.1", port=1, timeout=0.5)
    assert client.ping() is False


# --------------------------------------------------------------------------- #
# Factory wiring + macOS safety
# --------------------------------------------------------------------------- #
def test_factory_builds_remote_mt5():
    from src.execution.factory import get_execution_handler
    h = get_execution_handler("remote_mt5", host="127.0.0.1", port=9099)
    assert isinstance(h, RemoteMT5ExecutionHandler)


def test_remote_handler_does_not_import_metatrader5():
    import sys
    # Importing/constructing the remote client must never load MetaTrader5.
    RemoteMT5ExecutionHandler(host="127.0.0.1", port=9099)
    assert "MetaTrader5" not in sys.modules
