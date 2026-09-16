"""ExecutionHandler — abstract interface (README §13).

The entire analytical engine (signal generator, risk manager, backtester) depends
on THIS interface only — never on `MetaTrader5` directly. That is what lets the
whole system run and backtest on macOS with no MT5/Wine/Docker, and makes swapping
mock <-> real a one-line config change.

Three implementations exist (selected by settings.EXECUTION_HANDLER via the factory):
  * MockExecutionHandler      — pure Python: dev, tests, backtests, paper orders (mock.py)
  * MT5ExecutionHandler       — real broker via MetaTrader5; runs only on the Windows
                                host with the terminal (mt5.py; Wine is a proven dead
                                end — docs/WINE_VERDICT.md)
  * RemoteMT5ExecutionHandler — RPC client in the engine -> MT5 host (remote_mt5.py)

Volume convention: every handler takes and returns ``volume`` in UNITS of the
base currency (e.g. 10_000 = 0.1 standard lot) — the unit the RiskManager sizes
in. MT5ExecutionHandler converts to broker lots internally.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ExecutionHandler(ABC):
    """Abstract contract every execution backend must satisfy."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish the broker/session connection. Returns True on success."""

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: float,
        tp: float,
        price: float | None = None,
    ) -> dict:
        """Place a market order.

        Args:
            symbol: instrument, e.g. "EURUSD".
            side:   "BUY" or "SELL".
            volume: position size in UNITS of the base currency (not lots).
            sl:     stop-loss price.
            tp:     take-profit price.
            price:  fill price to simulate against (MockExecutionHandler needs
                    this for backtesting). The real MT5 handler ignores it and
                    fills at the live market price.

        Returns a dict describing the result, including at least:
            {"ticket": int, "symbol", "side", "volume", "price", "sl", "tp",
             "status": "filled" | "rejected", ...}
        """

    @abstractmethod
    def get_open_positions(self) -> list:
        """Return the list of currently open positions (dicts)."""

    @abstractmethod
    def close_position(self, ticket: int, price: float | None = None) -> dict:
        """Close the position identified by ``ticket``; return a result dict.

        ``price`` is the fill price to close against (the mock needs it for
        backtesting; the real MT5 handler ignores it and uses the live price).
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the broker/session connection."""
