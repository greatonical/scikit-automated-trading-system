"""RiskManager — Module 5 (README §10 step 5 / §7).

Decides HOW MUCH to trade and WHERE to put the stop, and enforces hard limits so
one bad run can't wipe the account. The signal layer says *what* to do; this
layer keeps it *safe*.

Three jobs (README §7):

  1. **Position sizing — fixed-fractional.** Risk a fixed % of current equity per
     trade (not a fixed lot size). When equity shrinks, trade size shrinks too,
     which curbs catastrophic drawdown.
  2. **Dynamic stop-loss.** Normally the stop sits a configured % away. When
     volatility is abnormal (large |Z-Score|), TIGHTEN the stop so a violent move
     hurts less.
  3. **Hard limits.** Block new trades once the daily loss limit or the maximum
     drawdown ceiling (< 15%) is hit.

All numbers come from config/settings.py (README §12).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class TradePlan:
    """Sizing + stop/target for one prospective trade."""

    side: str            # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float        # units to trade (fixed-fractional sized)
    risk_amount: float   # cash risked if the stop is hit


def dynamic_stop_pct(
    base_pct: float, volume_zscore: float, trigger: float, factor: float
) -> float:
    """Stop distance (fraction of price) after the dynamic-tightening rule.

    ``base_pct * factor`` when |volume Z-Score| >= ``trigger``, else ``base_pct``.
    Shared by the RiskManager (actual stops) and the triple-barrier label (when
    LABEL_DYNAMIC_SL is on) so both apply the identical rule.
    """
    if abs(volume_zscore) >= trigger:
        return base_pct * factor
    return base_pct


class RiskManager:
    """Position sizing, dynamic stops, and account-level safety limits."""

    def __init__(
        self,
        starting_equity: float | None = None,
        risk_fraction: float | None = None,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        max_drawdown_limit: float | None = None,
        daily_loss_limit: float | None = None,
        dynamic_sl_zscore_trigger: float | None = None,
        dynamic_sl_tighten_factor: float | None = None,
    ) -> None:
        self.starting_equity = (
            starting_equity if starting_equity is not None else settings.STARTING_EQUITY
        )
        self.risk_fraction = (
            risk_fraction if risk_fraction is not None
            else settings.RISK_FRACTION_PER_TRADE
        )
        self.stop_loss_pct = (
            stop_loss_pct if stop_loss_pct is not None else settings.DEFAULT_STOP_LOSS_PCT
        )
        self.take_profit_pct = (
            take_profit_pct if take_profit_pct is not None
            else settings.DEFAULT_TAKE_PROFIT_PCT
        )
        self.max_drawdown_limit = (
            max_drawdown_limit if max_drawdown_limit is not None
            else settings.MAX_DRAWDOWN_LIMIT
        )
        self.daily_loss_limit = (
            daily_loss_limit if daily_loss_limit is not None
            else settings.DAILY_LOSS_LIMIT
        )
        self.dynamic_sl_trigger = (
            dynamic_sl_zscore_trigger if dynamic_sl_zscore_trigger is not None
            else settings.DYNAMIC_SL_ZSCORE_TRIGGER
        )
        self.dynamic_sl_factor = (
            dynamic_sl_tighten_factor if dynamic_sl_tighten_factor is not None
            else settings.DYNAMIC_SL_TIGHTEN_FACTOR
        )

        # Equity tracking for drawdown / daily-loss enforcement.
        self.equity = self.starting_equity
        self.peak_equity = self.starting_equity
        self._day_start_equity = self.starting_equity

    # ------------------------------------------------------------------ #
    # Stop-loss distance (dynamic)
    # ------------------------------------------------------------------ #
    def stop_distance_pct(self, volume_zscore: float) -> float:
        """Stop-loss distance as a fraction of price.

        Default ``stop_loss_pct``, tightened by ``dynamic_sl_factor`` when the
        absolute Z-Score exceeds the trigger (abnormal volatility -> smaller stop).
        """
        stop = dynamic_stop_pct(
            self.stop_loss_pct, volume_zscore,
            self.dynamic_sl_trigger, self.dynamic_sl_factor,
        )
        if stop != self.stop_loss_pct:
            logger.info(
                "Volatility spike (|z|=%.2f >= %.2f): tightening stop %.4f -> %.4f",
                abs(volume_zscore), self.dynamic_sl_trigger,
                self.stop_loss_pct, stop,
            )
        return stop

    # ------------------------------------------------------------------ #
    # Position sizing (fixed-fractional)
    # ------------------------------------------------------------------ #
    def size_position(
        self, side: str, entry_price: float, volume_zscore: float = 0.0,
        atr: float | None = None,
    ) -> TradePlan:
        """Build a TradePlan: fixed-fractional volume + stop/target prices.

        Cash risked = equity * risk_fraction. Volume = risk_amount / per-unit
        risk (the price distance to the stop). Stop/target are placed on the
        correct side for BUY vs SELL.

        If ``USE_ATR_STOPS`` is on and an ``atr`` is given, the SL/TP distances are
        volatility-scaled (ATR × multiple) instead of a flat %, matching the
        triple-barrier label so trained labels and live trades agree.
        """
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {side!r}")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")

        risk_amount = self.equity * self.risk_fraction

        if settings.USE_ATR_STOPS and atr is not None and atr > 0:
            sl_dist = atr * settings.ATR_SL_MULTIPLE
            tp_dist = atr * settings.ATR_TP_MULTIPLE
        else:
            sl_dist = entry_price * self.stop_distance_pct(volume_zscore)
            tp_dist = entry_price * self.take_profit_pct

        per_unit_risk = sl_dist
        volume = risk_amount / per_unit_risk if per_unit_risk > 0 else 0.0

        if side == "BUY":
            stop_loss = entry_price - sl_dist
            take_profit = entry_price + tp_dist
        else:  # SELL
            stop_loss = entry_price + sl_dist
            take_profit = entry_price - tp_dist

        plan = TradePlan(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume=volume,
            risk_amount=risk_amount,
        )
        logger.info(
            "Sized %s @ %.5f: vol=%.2f risk=%.2f sl=%.5f tp=%.5f",
            side, entry_price, volume, risk_amount, stop_loss, take_profit,
        )
        return plan

    # ------------------------------------------------------------------ #
    # Equity tracking + hard limits
    # ------------------------------------------------------------------ #
    def update_equity(self, new_equity: float) -> None:
        """Record a new equity value and update the running peak."""
        self.equity = new_equity
        self.peak_equity = max(self.peak_equity, new_equity)

    def start_new_day(self) -> None:
        """Reset the daily-loss baseline (call at the start of each trading day)."""
        self._day_start_equity = self.equity

    def current_drawdown(self) -> float:
        """Drawdown from the peak, as a fraction (0.10 == 10% below peak)."""
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity

    def daily_loss(self) -> float:
        """Loss so far today, as a fraction of the day's starting equity."""
        if self._day_start_equity <= 0:
            return 0.0
        return (self._day_start_equity - self.equity) / self._day_start_equity

    def can_trade(self) -> bool:
        """False if a hard limit (max drawdown or daily loss) is breached."""
        if self.current_drawdown() >= self.max_drawdown_limit:
            logger.warning(
                "Trading halted: drawdown %.2f%% >= limit %.2f%%",
                self.current_drawdown() * 100, self.max_drawdown_limit * 100,
            )
            return False
        if self.daily_loss() >= self.daily_loss_limit:
            logger.warning(
                "Trading halted: daily loss %.2f%% >= limit %.2f%%",
                self.daily_loss() * 100, self.daily_loss_limit * 100,
            )
            return False
        return True
