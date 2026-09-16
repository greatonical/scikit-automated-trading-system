"""Backtester — Module 7 (README §10 step 7 / §8).

Replays historical candles through the FULL pipeline and measures performance:

    candle -> SignalGenerator (hybrid) -> RiskManager (size + stops)
           -> MockExecutionHandler (fill, SL/TP, P&L) -> metrics

It runs against the abstract ExecutionHandler (the mock by default), so the whole
engine is proven end-to-end on macOS with no MT5/Wine/Docker. Spread and slippage
are modelled in the handler so the metrics reflect realistic costs, not idealised
fills (see docs/RECOMMENDATIONS.md). Backtests always use the mock: a live broker
can't fill at historical prices or replay bar-by-bar SL/TP.

Outputs the README §8 metrics: Win Rate (with a Wilson confidence interval), Max
Drawdown, Profit Factor, Sharpe, plus net P&L and trade count, with a pass/fail
against the configured targets.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import pandas as pd

from config import settings
from src.execution.base import ExecutionHandler
from src.execution.mock import MockExecutionHandler
from src.risk_manager import RiskManager
from src.signal_generator import Action, SignalGenerator

logger = logging.getLogger(__name__)


def wilson_interval(wins: int, n: int, z: float | None = None) -> tuple[float, float]:
    """Wilson score interval for a win rate of ``wins`` / ``n`` (z from config).

    With the 30–40 trades a held-out backtest produces this interval is wide, so
    it is reported next to every win rate rather than the point estimate alone.
    """
    if n <= 0:
        return (0.0, 0.0)
    z = settings.WIN_RATE_CI_Z if z is None else z
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - half) / denom, (centre + half) / denom)


@dataclass
class BacktestResult:
    """Summary of a backtest run."""

    n_trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    profit_factor: float
    max_drawdown: float
    sharpe: float
    final_equity: float
    win_rate_ci_low: float = 0.0
    win_rate_ci_high: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {
            "n_trades": self.n_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "win_rate_ci_low": round(self.win_rate_ci_low, 4),
            "win_rate_ci_high": round(self.win_rate_ci_high, 4),
            "net_pnl": round(self.net_pnl, 2),
            "profit_factor": round(self.profit_factor, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe": round(self.sharpe, 4),
            "final_equity": round(self.final_equity, 2),
        }
        return d

    def meets_targets(self) -> dict[str, bool]:
        """Check each metric against the README §8 target."""
        return {
            "win_rate": self.win_rate > settings.TARGET_WIN_RATE,
            "max_drawdown": self.max_drawdown < settings.TARGET_MAX_DRAWDOWN,
            "profit_factor": self.profit_factor > settings.TARGET_PROFIT_FACTOR,
            "sharpe": self.sharpe > settings.TARGET_SHARPE,
        }


class Backtester:
    """Event-driven backtester over OHLCV candles + model probabilities."""

    def __init__(
        self,
        signal_generator: SignalGenerator | None = None,
        risk_manager: RiskManager | None = None,
        execution_handler: ExecutionHandler | None = None,
        symbol: str = "EURUSD",
        use_time_exit: bool | None = None,
        time_exit_bars: int | None = None,
    ) -> None:
        self.signals = signal_generator or SignalGenerator()
        self.risk = risk_manager or RiskManager()
        self.exec = execution_handler or MockExecutionHandler()
        self.symbol = symbol
        # Time exit = the triple-barrier label's vertical barrier (see settings).
        use_time_exit = (
            settings.USE_TIME_EXIT if use_time_exit is None else use_time_exit
        )
        self.time_exit_bars = (
            (time_exit_bars if time_exit_bars is not None
             else settings.TRIPLE_BARRIER_MAX_HOLD)
            if use_time_exit else None
        )
        # Per-ticket bookkeeping (entry/exit time, bars held, exit reason).
        self._trade_meta: dict[int, dict] = {}

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    def run(self, df: pd.DataFrame, probabilities) -> BacktestResult:
        """Replay ``df`` (must include OHLC + ZScore_Volume) with ``probabilities``.

        For each candle, in order:
          1. Update SL/TP exits for any open positions using this bar's High/Low,
             then (if enabled) the time exit at this bar's Close.
          2. If allowed by risk limits and no position is open, ask the signal
             layer for a decision; if BUY/SELL, size it and place the order.
        At the end, force-close any still-open position at the last Close.
        """
        probs = list(probabilities)
        if len(probs) != len(df):
            raise ValueError("probabilities length must match df rows")

        self.exec.connect()
        self._trade_meta = {}
        equity = self.risk.starting_equity
        equity_curve = [equity]
        current_day = None

        for i, (ts, row) in enumerate(df.iterrows()):
            # 0) Reset the daily-loss baseline when the calendar day changes, so
            #    a halt from one bad day doesn't freeze trading forever.
            day = ts.date() if hasattr(ts, "date") else None
            if day != current_day:
                current_day = day
                self.risk.start_new_day()

            # 1) Exits: stop-loss / take-profit touched within this bar, then the
            #    time exit (the label's vertical barrier) if enabled.
            exits = [(f, f.get("exit_reason")) for f in self._update_exits(row)]
            exits += [(f, "time_exit") for f in self._time_exits(i, row)]
            for fill, reason in exits:
                self._record_exit(fill["ticket"], i, ts, reason)
                equity += fill["pnl"]
                self.risk.update_equity(equity)
                equity_curve.append(equity)

            # 2) Consider a new entry (one position at a time for clarity).
            if not self.risk.can_trade():
                continue
            if self.exec.get_open_positions():
                continue

            signal = self.signals.decide(
                probability=probs[i],
                volume_zscore=row["ZScore_Volume"],
                timestamp=ts,
            )
            if signal.action is Action.HOLD:
                continue

            self._open_trade(signal, row, i)

        # Close anything still open at the final price.
        equity = self._force_close_remaining(df, equity, equity_curve)
        self.exec.disconnect()

        return self._summarise(equity_curve)

    # ------------------------------------------------------------------ #
    # Steps
    # ------------------------------------------------------------------ #
    def _update_exits(self, row) -> list[dict]:
        if hasattr(self.exec, "check_sl_tp"):
            return self.exec.check_sl_tp(self.symbol, high=row["High"], low=row["Low"])
        return []

    def _time_exits(self, bar_index: int, row) -> list[dict]:
        """Close positions held ``time_exit_bars`` bars, at this bar's Close."""
        if self.time_exit_bars is None:
            return []
        fills = []
        for pos in self.exec.get_open_positions():
            meta = self._trade_meta.get(pos["ticket"])
            if meta is not None and bar_index - meta["entry_bar"] >= self.time_exit_bars:
                fills.append(self.exec.close_position(pos["ticket"], price=row["Close"]))
        return fills

    def _open_trade(self, signal, row, bar_index: int) -> None:
        plan = self.risk.size_position(
            side=signal.action.value,
            entry_price=row["Close"],
            volume_zscore=row["ZScore_Volume"],
            atr=row["ATR"] if "ATR" in row.index else None,
        )
        res = self.exec.place_order(
            symbol=self.symbol,
            side=plan.side,
            volume=plan.volume,
            sl=plan.stop_loss,
            tp=plan.take_profit,
            price=plan.entry_price,
        )
        if res.get("status") == "filled":
            self._trade_meta[res["ticket"]] = {
                "entry_time": row.name, "entry_bar": bar_index,
            }

    def _record_exit(self, ticket: int, bar_index: int, ts, reason: str | None) -> None:
        meta = self._trade_meta.setdefault(ticket, {})
        meta["exit_time"] = ts
        if "entry_bar" in meta:
            meta["bars_held"] = bar_index - meta["entry_bar"]
        if reason is not None:
            meta["exit_reason"] = reason

    def _force_close_remaining(self, df, equity, equity_curve) -> float:
        for pos in self.exec.get_open_positions():
            res = self.exec.close_position(pos["ticket"], price=df["Close"].iloc[-1])
            self._record_exit(pos["ticket"], len(df) - 1, df.index[-1], "end_of_data")
            equity += res["pnl"]
            self.risk.update_equity(equity)
            equity_curve.append(equity)
        return equity

    # ------------------------------------------------------------------ #
    # Metrics (README §8)
    # ------------------------------------------------------------------ #
    def _summarise(self, equity_curve: list[float]) -> BacktestResult:
        trades = [
            {**t, **self._trade_meta.get(t["ticket"], {})}
            for t in getattr(self.exec, "closed_trades", [])
        ]
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        n = len(pnls)
        win_rate = len(wins) / n if n else 0.0
        ci_low, ci_high = wilson_interval(len(wins), n)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else (math.inf if gross_profit > 0 else 0.0)
        )
        net_pnl = sum(pnls)

        return BacktestResult(
            n_trades=n,
            wins=len(wins),
            losses=len(losses),
            win_rate=win_rate,
            net_pnl=net_pnl,
            profit_factor=profit_factor,
            max_drawdown=self._max_drawdown(equity_curve),
            sharpe=self._sharpe(equity_curve),
            final_equity=equity_curve[-1] if equity_curve else 0.0,
            win_rate_ci_low=ci_low,
            win_rate_ci_high=ci_high,
            equity_curve=equity_curve,
            trades=trades,
        )

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        """Largest peak-to-trough drop, as a fraction of the peak."""
        peak = -math.inf
        max_dd = 0.0
        for eq in equity_curve:
            peak = max(peak, eq)
            if peak > 0:
                max_dd = max(max_dd, (peak - eq) / peak)
        return max_dd

    @staticmethod
    def _sharpe(equity_curve: list[float]) -> float:
        """Sharpe-like ratio from per-step equity returns (rf=0, unannualised).

        The equity curve only moves when a trade closes, so this is effectively a
        PER-TRADE Sharpe — not the annualised figure the report's > 1.0 target
        conventionally refers to. State the convention wherever it's quoted.
        """
        if len(equity_curve) < 3:
            return 0.0
        series = pd.Series(equity_curve)
        returns = series.pct_change().dropna()
        std = returns.std(ddof=1)
        if std == 0 or math.isnan(std):
            return 0.0
        return float(returns.mean() / std)
