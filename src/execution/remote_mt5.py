"""RemoteMT5ExecutionHandler — RPC client (runs in the ENGINE).

Implements the ExecutionHandler interface but forwards every call over a TCP
socket to the rpc server (src/execution/mt5_service.py) on the MT5 host — a
native Windows machine, since Wine proved a dead end (docs/WINE_VERDICT.md). The
engine uses THIS to drive real MT5 without ever importing MetaTrader5 — so it
runs on macOS/Linux unchanged.

Only stdlib `socket` is used here. If the MT5 host is unreachable, calls raise
ConnectionError with a clear message so the dashboard can degrade gracefully
instead of crashing. Requests carry MT5_RPC_TOKEN when it is set.
"""
from __future__ import annotations

import logging
import socket

from config import settings
from src.execution import rpc_protocol as rpc
from src.execution.base import ExecutionHandler

logger = logging.getLogger(__name__)


class RemoteMT5ExecutionHandler(ExecutionHandler):
    """Talks to the mt5 container's RPC server over TCP."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float = 10.0,
        token: str | None = None,
    ) -> None:
        self.host = host or getattr(settings, "MT5_RPC_HOST", rpc.DEFAULT_HOST)
        self.port = port or getattr(settings, "MT5_RPC_PORT", rpc.DEFAULT_PORT)
        self.timeout = timeout
        self.token = token if token is not None else settings.MT5_RPC_TOKEN

    # ------------------------------------------------------------------ #
    # Transport
    # ------------------------------------------------------------------ #
    def _call(self, method: str, **args):
        """Send one RPC request and return the result (or raise)."""
        request = rpc.make_request(method, token=self.token, **args)
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                sock.sendall(rpc.encode(request))
                data = self._recv_line(sock)
        except OSError as exc:
            raise ConnectionError(
                f"MT5 service unreachable at {self.host}:{self.port}. Start the RPC "
                f"server on the MT5 host (`python -m src.execution.mt5_service`). ({exc})"
            ) from exc

        response = rpc.decode(data)
        if not response.get("ok"):
            raise RuntimeError(f"MT5 RPC error: {response.get('error')}")
        return response.get("result")

    @staticmethod
    def _recv_line(sock: socket.socket) -> bytes:
        """Read until newline (one response message)."""
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        return b"".join(chunks)

    # ------------------------------------------------------------------ #
    # ExecutionHandler interface (forwarded over RPC)
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        return bool(self._call("connect"))

    def place_order(
        self, symbol: str, side: str, volume: float,
        sl: float, tp: float, price: float | None = None,
    ) -> dict:
        return self._call(
            "place_order", symbol=symbol, side=side, volume=volume,
            sl=sl, tp=tp, price=price,
        )

    def get_open_positions(self) -> list:
        return self._call("get_open_positions")

    def close_position(self, ticket: int, price: float | None = None) -> dict:
        return self._call("close_position", ticket=ticket, price=price)

    def disconnect(self) -> None:
        self._call("disconnect")

    # ------------------------------------------------------------------ #
    # Convenience for the dashboard's "Live" status indicator
    # ------------------------------------------------------------------ #
    def ping(self) -> bool:
        """True if the mt5 RPC server is reachable, False otherwise (no raise)."""
        try:
            self._call("ping")
            return True
        except (ConnectionError, RuntimeError, OSError):
            return False
