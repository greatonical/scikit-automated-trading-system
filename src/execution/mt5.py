"""MT5ExecutionHandler — Module 8 (README §10 step 8 / §13).

The REAL broker implementation of the ExecutionHandler interface. It imports the
Windows-only `MetaTrader5` package and therefore runs ONLY on a Windows host with
the MT5 terminal installed. (The Wine/Docker container in docker/mt5/ was proven a
dead end: `mt5.initialize()` fails with -10005 under Wine — docs/WINE_VERDICT.md.)
It is never imported on macOS — the factory (src/execution/factory.py) imports
this module lazily, and `MetaTrader5` itself is imported lazily inside connect()
so that even importing this file stays safe.

Demo account only (README §9). Credentials come from settings (loaded from the
gitignored .env), never hardcoded.

Volume: the engine speaks UNITS of base currency (the RiskManager's unit); MT5
speaks LOTS. This class converts using the broker's own symbol_info (contract
size, volume step/min/max), rounding DOWN so a live order never exceeds the risk
the RiskManager sized for.
"""
from __future__ import annotations

import logging
import math

from config import settings
from src.execution.base import ExecutionHandler

logger = logging.getLogger(__name__)


class MT5ExecutionHandler(ExecutionHandler):
    """Routes orders to a real (demo) MT5 terminal via the MetaTrader5 API."""

    def __init__(
        self,
        login: str | None = None,
        password: str | None = None,
        server: str | None = None,
    ) -> None:
        self.login = login or settings.MT5_LOGIN
        self.password = password or settings.MT5_PASSWORD
        self.server = server or settings.MT5_SERVER
        self._mt5 = None          # the MetaTrader5 module, imported in connect()
        self.connected = False

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def connect(self) -> bool:
        """Initialise the MT5 terminal and log in to the demo account.

        `MetaTrader5` is imported HERE (lazily) so this module stays importable
        on macOS for type-checking/tests; the import only actually runs inside
        the Wine container where the package exists.
        """
        try:
            import MetaTrader5 as mt5  # noqa: N813  (Windows-only, container)
        except ImportError as exc:  # pragma: no cover - never hit on macOS
            raise RuntimeError(
                "MetaTrader5 is unavailable. MT5ExecutionHandler runs only inside "
                "a Windows environment with the MT5 terminal (see docs/WINE_VERDICT.md). "
                "Use EXECUTION_HANDLER='mock' (paper) or 'remote_mt5' (RPC to the "
                "Windows host) elsewhere."
            ) from exc

        self._mt5 = mt5
        if not self.login or not self.password or not self.server:
            raise RuntimeError(
                "Missing MT5 demo credentials. Set MT5_LOGIN/PASSWORD/SERVER in .env."
            )

        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")

        authorized = mt5.login(
            login=int(self.login), password=self.password, server=self.server
        )
        if not authorized:
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")

        self.connected = True
        logger.info("MT5 connected: login=%s server=%s", self.login, self.server)
        return True

    def disconnect(self) -> None:
        if self._mt5 is not None and self.connected:
            self._mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected.")

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
        """Send a market order to MT5. ``price`` is ignored — MT5 fills live.

        ``volume`` is in UNITS (the engine's convention) and is converted to lots
        with the broker's symbol_info; returned ``volume`` is the units actually
        sent (after rounding down to the lot step), ``lots`` the broker volume.
        """
        self._require_connected()
        mt5 = self._mt5
        side = side.upper()

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"symbol": symbol, "status": "rejected", "reason": "no_tick"}

        if side == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            fill_price = tick.ask
        elif side == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            fill_price = tick.bid
        else:
            raise ValueError(f"side must be BUY or SELL, got {side!r}")

        info = mt5.symbol_info(symbol)
        if info is None:
            return {"symbol": symbol, "status": "rejected", "reason": "no_symbol_info"}
        lots = self._units_to_lots(volume, info)
        if lots is None:
            return {
                "symbol": symbol, "side": side, "volume": volume,
                "status": "rejected", "reason": "below_min_volume",
            }

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lots,
            "type": order_type,
            "price": fill_price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": settings.MT5_DEVIATION_POINTS,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        logger.info(
            "MT5 order %s %s units=%.0f lots=%.2f -> %s",
            side, symbol, volume, lots,
            "filled" if ok else f"rejected({getattr(result, 'retcode', '?')})",
        )
        return {
            "ticket": getattr(result, "order", None),
            "symbol": symbol,
            "side": side,
            "volume": lots * self._contract_size(info),
            "lots": lots,
            "price": getattr(result, "price", fill_price),
            "sl": sl,
            "tp": tp,
            "status": "filled" if ok else "rejected",
            "retcode": getattr(result, "retcode", None),
        }

    def get_open_positions(self) -> list:
        self._require_connected()
        positions = self._mt5.positions_get()
        if positions is None:
            return []
        out = []
        for p in positions:
            info = self._mt5.symbol_info(p.symbol)
            contract = (
                self._contract_size(info) if info is not None
                else settings.FX_STANDARD_LOT_UNITS
            )
            out.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "side": "BUY" if p.type == self._mt5.POSITION_TYPE_BUY else "SELL",
                "volume": p.volume * contract,   # units (engine convention)
                "lots": p.volume,
                "price": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
            })
        return out

    def close_position(self, ticket: int, price: float | None = None) -> dict:
        """Close an open position by ticket (``price`` ignored — MT5 fills live)."""
        self._require_connected()
        mt5 = self._mt5

        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"ticket": ticket, "status": "not_found"}
        pos = positions[0]

        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return {"ticket": ticket, "symbol": pos.symbol,
                    "status": "failed", "reason": "no_tick"}

        # Closing means sending the opposite side at the current price.
        if pos.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            close_price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            close_price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,           # already lots (broker's own number)
            "type": close_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": settings.MT5_DEVIATION_POINTS,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        logger.info("MT5 close #%s -> %s", ticket, "closed" if ok else "failed")
        return {
            "ticket": ticket,
            "symbol": pos.symbol,
            "status": "closed" if ok else "failed",
            "exit_price": getattr(result, "price", close_price),
            "retcode": getattr(result, "retcode", None),
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _contract_size(info) -> float:
        """Units per 1.0 lot for this symbol (broker value, else standard lot)."""
        return float(
            getattr(info, "trade_contract_size", 0) or settings.FX_STANDARD_LOT_UNITS
        )

    @classmethod
    def _units_to_lots(cls, units: float, info) -> float | None:
        """Convert engine units to broker lots, rounded DOWN to the volume step.

        Rounding down (and clamping to volume_max) never exceeds the risk the
        RiskManager sized for. Returns None if the result is below the broker's
        minimum lot — the order is then rejected rather than silently enlarged.
        """
        step = float(getattr(info, "volume_step", 0) or 0.01)
        raw = units / cls._contract_size(info)
        lots = math.floor(raw / step + 1e-9) * step
        decimals = max(0, -int(math.floor(math.log10(step))))
        lots = round(lots, decimals)
        if lots < float(getattr(info, "volume_min", step)):
            return None
        return min(lots, float(getattr(info, "volume_max", lots)))

    def _require_connected(self) -> None:
        if not self.connected or self._mt5 is None:
            raise RuntimeError("Not connected. Call connect() first.")
