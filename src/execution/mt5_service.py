"""MT5 RPC service — runs on the MT5 host (README §13).

Listens on a TCP socket and forwards each request to a real MT5ExecutionHandler
(which calls the Windows-only MetaTrader5 API). The engine's
RemoteMT5ExecutionHandler is the client. This is the documented thin RPC boundary
between the Linux/macOS engine and the Windows-side execution layer.

Where it runs: a native Windows host with the MT5 terminal. The Wine/Docker
container route (docker/mt5/) is a documented dead end — docs/WINE_VERDICT.md.

Security: if MT5_RPC_TOKEN is set, every request must carry it; otherwise any
host that can reach the port can place orders. The token travels in clear text,
so keep the port private (LAN, VPN or SSH tunnel) either way.

Demo account only (README §9); credentials come from the gitignored .env.

Run (on the MT5 host, from the project root): python -m src.execution.mt5_service
"""
from __future__ import annotations

import logging
import socketserver

from config import settings
from src.execution import rpc_protocol as rpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mt5_service")

# One shared handler for the single MT5 terminal instance (README §13).
_handler = None


def _get_handler():
    """Lazily create + connect the real MT5 handler (single instance)."""
    global _handler
    if _handler is None:
        from src.execution.mt5 import MT5ExecutionHandler

        h = MT5ExecutionHandler()
        h.connect()
        _handler = h
        logger.info("MT5 handler connected and ready for RPC.")
    return _handler


def dispatch(method: str, args: dict) -> dict:
    """Map an RPC method name to the handler call; return a response dict."""
    try:
        if method == "ping":
            return rpc.ok_response("pong")

        handler = _get_handler()

        if method == "connect":
            return rpc.ok_response(True)  # already connected on first use
        if method == "place_order":
            return rpc.ok_response(handler.place_order(**args))
        if method == "get_open_positions":
            return rpc.ok_response(handler.get_open_positions())
        if method == "close_position":
            return rpc.ok_response(handler.close_position(**args))
        if method == "disconnect":
            handler.disconnect()
            return rpc.ok_response(None)

        return rpc.error_response(f"unknown method: {method}")
    except Exception as exc:  # noqa: BLE001 - report back to the client
        logger.exception("RPC %s failed", method)
        return rpc.error_response(f"{type(exc).__name__}: {exc}")


class _RPCHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
        try:
            request = rpc.decode(line)
        except Exception as exc:  # noqa: BLE001
            self.wfile.write(rpc.encode(rpc.error_response(f"bad request: {exc}")))
            return
        expected = settings.MT5_RPC_TOKEN
        if expected and not rpc.token_ok(request, expected):
            logger.warning("Rejected RPC with a missing/wrong token from %s",
                           self.client_address[0])
            self.wfile.write(rpc.encode(rpc.error_response("unauthorized")))
            return
        response = dispatch(request.get("method", ""), request.get("args", {}))
        self.wfile.write(rpc.encode(response))


class _Server(socketserver.ThreadingTCPServer):
    # Class attributes on purpose: they take effect at bind time inside
    # __init__ (setting allow_reuse_address on an instance is too late).
    allow_reuse_address = True
    daemon_threads = True


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or rpc.DEFAULT_HOST
    port = port or settings.MT5_RPC_PORT
    if not settings.MT5_RPC_TOKEN:
        logger.warning(
            "MT5_RPC_TOKEN is not set: any host that can reach port %d can place "
            "orders on this account. Set it in .env and keep the port private.", port,
        )
    logger.info("MT5 RPC service listening on %s:%d", host, port)
    with _Server((host, port), _RPCHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    serve()
