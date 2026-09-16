"""MockExecutionHandler — pure-Python simulated broker (README §13).

Used for ALL development, unit tests, and backtesting on macOS. No MT5, no Wine,
no Docker. It mimics the real handler's behaviour and return shapes so the
backtester and engine can run end-to-end offline, and swapping to the real MT5
handler later requires no engine changes.

What it simulates:
  * Filling market orders at a given price (optionally with spread/slippage).
  * Tracking open positions in memory with a unique ticket per position.
  * Closing positions and computing realised P&L.
  * Checking each open position against its stop-loss / take-profit on a price
    update (so the backtester can drive SL/TP exits bar by bar).
"""
from __future__ import annotations

import logging

from src.execution.base import ExecutionHandler

logger = logging.getLogger(__name__)


class MockExecutionHandler(ExecutionHandler):
    """In-memory broker simulation."""

    def __init__(self, spread: float = 0.0, slippage: float = 0.0) -> None:
        # spread/slippage are price units applied against the trader on fills,
        # so the backtest can reflect real costs (default 0 = frictionless).
        self.spread = spread
        self.slippage = slippage
        self.connected = False
        self._next_ticket = 1
        self._positions: dict[int, dict] = {}
        self._closed: list[dict] = []

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        self.connected = True
        logger.info("MockExecutionHandler connected.")
        return True

    def disconnect(self) -> None:
        self.connected = False
        logger.info("MockExecutionHandler disconnected.")

    # ------------------------------------------------------------------ #
    # Orders
    # ------------------------------------------------------------------ #
    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        sl: float,
        tp: float,
        price: float | None = None,
    ) -> dict:
        """Open a simulated position. ``price`` is the market price to fill at.

        The fill price includes spread + slippage moved AGAINST the trader:
        a BUY fills slightly higher, a SELL slightly lower.
        """
        if not self.connected:
            raise RuntimeError("Not connected. Call connect() first.")
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {side!r}")
        if price is None:
            raise ValueError("MockExecutionHandler requires a fill price")

        cost = self.spread + self.slippage
        fill_price = price + cost if side == "BUY" else price - cost

        ticket = self._next_ticket
        self._next_ticket += 1
        position = {
            "ticket": ticket,
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "price": fill_price,       # entry fill
            "sl": sl,
            "tp": tp,
            "status": "filled",
        }
        self._positions[ticket] = position
        logger.info(
            "MOCK order filled: #%d %s %s vol=%.2f @ %.5f sl=%.5f tp=%.5f",
            ticket, side, symbol, volume, fill_price, sl, tp,
        )
        return dict(position)

    def get_open_positions(self) -> list:
        return [dict(p) for p in self._positions.values()]

    def close_position(self, ticket: int, price: float | None = None) -> dict:
        """Close a position at ``price`` and record realised P&L."""
        if ticket not in self._positions:
            return {"ticket": ticket, "status": "not_found"}
        pos = self._positions.pop(ticket)
        if price is None:
            price = pos["price"]

        cost = self.spread + self.slippage
        # Closing a BUY = sell (fills lower); closing a SELL = buy (fills higher).
        exit_price = price - cost if pos["side"] == "BUY" else price + cost
        pnl = self._pnl(pos, exit_price)

        result = {
            **pos,
            "status": "closed",
            "exit_price": exit_price,
            "pnl": pnl,
        }
        self._closed.append(result)
        logger.info("MOCK closed #%d @ %.5f pnl=%.2f", ticket, exit_price, pnl)
        return result

    # ------------------------------------------------------------------ #
    # Backtest helpers (not part of the abstract interface)
    # ------------------------------------------------------------------ #
    def check_sl_tp(self, symbol: str, high: float, low: float) -> list[dict]:
        """Close any open position whose SL or TP was touched within [low, high].

        Drives bar-by-bar exits in the backtester. For a BUY: SL is below entry
        (triggered by ``low``), TP above (triggered by ``high``); reversed for a
        SELL. If both are touched in the same bar we conservatively assume the
        STOP hit first (worse case).
        """
        triggered = []
        for ticket, pos in list(self._positions.items()):
            sl, tp = pos["sl"], pos["tp"]
            if pos["side"] == "BUY":
                hit_sl = low <= sl
                hit_tp = high >= tp
                exit_price = sl if hit_sl else (tp if hit_tp else None)
            else:  # SELL
                hit_sl = high >= sl
                hit_tp = low <= tp
                exit_price = sl if hit_sl else (tp if hit_tp else None)
            if exit_price is not None:
                reason = "stop_loss" if hit_sl else "take_profit"
                res = self.close_position(ticket, price=exit_price)
                res["exit_reason"] = reason
                triggered.append(res)
        return triggered

    def _pnl(self, pos: dict, exit_price: float) -> float:
        """Realised P&L = price move in trade direction * volume."""
        if pos["side"] == "BUY":
            return (exit_price - pos["price"]) * pos["volume"]
        return (pos["price"] - exit_price) * pos["volume"]

    @property
    def closed_trades(self) -> list[dict]:
        return list(self._closed)
