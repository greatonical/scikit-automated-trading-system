"""Execution handler factory (README §13).

Swapping mock <-> real must be a SINGLE config change. `settings.EXECUTION_HANDLER`
("mock", "remote_mt5" or "mt5") decides which implementation live order routing
gets: the dashboard's Live mode calls `get_execution_handler()` and never imports a
concrete handler directly. (Backtests always use the mock — see settings.)

The MT5 handler is imported lazily inside the "mt5" branch so that `MetaTrader5`
(Windows-only) is never imported on macOS — importing this module stays safe.
"""
from __future__ import annotations

from config import settings
from src.execution.base import ExecutionHandler


def get_execution_handler(name: str | None = None, **kwargs) -> ExecutionHandler:
    """Return the configured ExecutionHandler instance.

    Args:
        name: "mock", "remote_mt5" or "mt5". Defaults to settings.EXECUTION_HANDLER.
        kwargs: forwarded to the chosen handler's constructor.
    """
    name = (name or settings.EXECUTION_HANDLER).lower()

    if name == "mock":
        from src.execution.mock import MockExecutionHandler
        return MockExecutionHandler(**kwargs)

    if name == "mt5":
        # Imported lazily — MetaTrader5 is Windows-only and must not load on macOS.
        # This handler runs on the Windows MT5 host, not in the engine.
        from src.execution.mt5 import MT5ExecutionHandler
        return MT5ExecutionHandler(**kwargs)

    if name == "remote_mt5":
        # RPC client — runs in the ENGINE, talks to the MT5 host over TCP.
        # stdlib sockets only; safe to import anywhere.
        from src.execution.remote_mt5 import RemoteMT5ExecutionHandler
        return RemoteMT5ExecutionHandler(**kwargs)

    raise ValueError(
        f"Unknown execution handler {name!r}. Use 'mock', 'mt5', or 'remote_mt5'."
    )
