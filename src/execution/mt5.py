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

# Broker rejection codes worth explaining rather than echoing as a bare number.
# Each of these was hit in production by a sibling project on the same broker family
# (docs/GADEL_ENGINE_COMPARISON.md).
RETCODE_HINTS = {
    10016: "invalid stops — SL/TP sits inside the symbol's minimum stop distance",
    10018: "market closed for this symbol",
    10019: "not enough money for the requested volume",
    10027: "AutoTrading is disabled — enable the Algo Trading button in the terminal",
    10030: "unsupported fill mode for this symbol",
}


class MT5ExecutionHandler(ExecutionHandler):
    """Routes orders to a real (demo) MT5 terminal via the MetaTrader5 API."""

    def __init__(
        self,
        login: str | None = None,
        password: str | None = None,
        server: str | None = None,
    ) -> None:
        # MT5 matches the server name letter-for-letter, spaces included: a stored
        # trailing space makes every login fail with a misleading error.
        self.login = (login or settings.MT5_LOGIN).strip()
        self.password = password or settings.MT5_PASSWORD
        self.server = (server or settings.MT5_SERVER).strip()
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

        # Attach to a SPECIFIC terminal when configured. With no path, MT5 attaches
        # to whichever terminal is already running — on a host that also runs a live
        # system that is the live terminal, and the login() below would then switch
        # THAT terminal's account. See MT5_TERMINAL_PATH in config/settings.py.
        init_kwargs = {}
        if settings.MT5_TERMINAL_PATH:
            init_kwargs["path"] = settings.MT5_TERMINAL_PATH
            logger.info("Attaching to MT5 terminal at %s", settings.MT5_TERMINAL_PATH)
        if not mt5.initialize(**init_kwargs):
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")

        authorized = mt5.login(
            login=int(self.login), password=self.password, server=self.server
        )
        if not authorized:
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {mt5.last_error()}")

        # Demo-only guard runs BEFORE connected=True, so no order can be placed on a
        # live account even if everything else is misconfigured (README §9).
        self._assert_demo_account(mt5)

        self.connected = True
        logger.info("MT5 connected: login=%s server=%s", self.login, self.server)
        return True

    def disconnect(self) -> None:
        if self._mt5 is not None and self.connected:
            self._mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected.")

    @staticmethod
    def _assert_demo_account(mt5) -> None:
        """Abort unless the logged-in account is a DEMO account (README §9).

        This is the last line of defence before real money: it runs after login and
        before ``connected`` is set, so a misconfigured login cannot reach
        ``place_order``. Disable only by deliberately setting MT5_REQUIRE_DEMO=false.
        """
        if not settings.MT5_REQUIRE_DEMO:
            logger.warning(
                "MT5_REQUIRE_DEMO is off — the demo-account guard is DISABLED. "
                "This system may now trade a live account."
            )
            return

        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            raise RuntimeError(
                "MT5 account_info() returned nothing, so the account type cannot be "
                "verified. Refusing to trade (README §9 allows demo accounts only)."
            )

        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        trade_mode = getattr(info, "trade_mode", None)
        if trade_mode != demo_mode:
            login = getattr(info, "login", "?")
            server = getattr(info, "server", "?")
            mt5.shutdown()
            raise RuntimeError(
                f"Refusing to trade: account {login} on {server} is NOT a demo "
                f"account (trade_mode={trade_mode}, demo={demo_mode}). This project "
                "is demo-only (README §9). If you truly intend to trade real money, "
                "you must set MT5_REQUIRE_DEMO=false deliberately."
            )

        logger.info(
            "Verified DEMO account: login=%s server=%s",
            getattr(info, "login", "?"), getattr(info, "server", "?"),
        )

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
            "magic": settings.MT5_MAGIC_NUMBER,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(mt5, info),
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        retcode = getattr(result, "retcode", None)
        logger.info(
            "MT5 order %s %s units=%.0f lots=%.2f -> %s",
            side, symbol, volume, lots,
            "filled" if ok else f"rejected({retcode}: {RETCODE_HINTS.get(retcode, '?')})",
        )
        out = {
            "ticket": getattr(result, "order", None),
            "symbol": symbol,
            "side": side,
            "volume": lots * self._contract_size(info),
            "lots": lots,
            "price": getattr(result, "price", fill_price),
            "sl": sl,
            "tp": tp,
            "status": "filled" if ok else "rejected",
            "retcode": retcode,
        }
        if not ok and retcode in RETCODE_HINTS:
            out["reason"] = RETCODE_HINTS[retcode]
        return out

    def get_open_positions(self) -> list:
        """Open positions. By default only ours (see MT5_ONLY_OWN_POSITIONS).

        MT5 reports magic 0 for hand-placed trades, so without this filter a human
        trading the same account would appear in — and could be closed by — our
        position list.
        """
        self._require_connected()
        positions = self._mt5.positions_get()
        if positions is None:
            return []
        out = []
        for p in positions:
            if not self._is_ours(p):
                continue
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
                "magic": getattr(p, "magic", 0),
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
        if not self._is_ours(pos):
            # Never close a trade the account owner placed by hand.
            return {"ticket": ticket, "symbol": pos.symbol, "status": "refused",
                    "reason": "position was not opened by this system"}

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
    def _is_ours(position) -> bool:
        """True if this position carries our magic number (or filtering is off)."""
        if not settings.MT5_ONLY_OWN_POSITIONS:
            return True
        return getattr(position, "magic", 0) == settings.MT5_MAGIC_NUMBER

    @staticmethod
    def _filling_mode(mt5, info):
        """Pick a fill mode the broker actually accepts for this symbol.

        ``symbol_info.filling_mode`` is a bitmask of the SYMBOL_FILLING_* flags.
        Requesting an unsupported mode is rejected with retcode 10030 — HFMarkets
        symbols, for instance, accept FOK only, so the IOC this handler used to
        hardcode would have bounced every live order.
        """
        mask = int(getattr(info, "filling_mode", 0) or 0)
        for flag, order_filling in (
            (getattr(mt5, "SYMBOL_FILLING_FOK", 1), getattr(mt5, "ORDER_FILLING_FOK", None)),
            (getattr(mt5, "SYMBOL_FILLING_IOC", 2), getattr(mt5, "ORDER_FILLING_IOC", None)),
        ):
            if mask & flag and order_filling is not None:
                return order_filling
        # Neither advertised: RETURN is the safe default for symbols that allow it.
        return getattr(mt5, "ORDER_FILLING_RETURN", mt5.ORDER_FILLING_IOC)

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
