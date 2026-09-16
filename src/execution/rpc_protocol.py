"""Tiny JSON-over-TCP protocol shared by the RPC server and client.

The engine (RemoteMT5ExecutionHandler) and the MT5 host (rpc server) speak
this. One request = one JSON object + newline; one response = one JSON object +
newline. Deliberately minimal — no external RPC framework needed.

Message shapes:
    request : {"method": "place_order", "args": {...}, "token": "..."}  (token optional)
    response: {"ok": true, "result": <any>}  |  {"ok": false, "error": "..."}

When the server has MT5_RPC_TOKEN set, requests must carry the same token. It is
sent in clear text (plain TCP), so it is defence-in-depth only — keep the port on
a private network or behind a VPN/SSH tunnel.
"""
from __future__ import annotations

import hmac
import json

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9099


def encode(obj: dict) -> bytes:
    """Serialise a message to a newline-terminated JSON line."""
    return (json.dumps(obj) + "\n").encode("utf-8")


def decode(line: bytes | str) -> dict:
    """Parse one JSON line into a dict."""
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    return json.loads(line)


def make_request(method: str, token: str | None = None, **args) -> dict:
    """Build a request; a non-empty ``token`` authenticates it to the server."""
    request = {"method": method, "args": args}
    if token:
        request["token"] = token
    return request


def token_ok(request: dict, expected: str) -> bool:
    """Constant-time comparison of a request's token with the server's secret."""
    given = str(request.get("token", "")).encode("utf-8")
    return hmac.compare_digest(given, expected.encode("utf-8"))


def ok_response(result) -> dict:
    return {"ok": True, "result": result}


def error_response(message: str) -> dict:
    return {"ok": False, "error": message}
