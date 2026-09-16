"""Tests for Backtester (Module 7).

Uses crafted candle sequences + forced probabilities so trade outcomes are
predictable, then checks the metrics and the README §8 scenario behaviours
(ranging = no trades; trending = trades; metrics computed correctly).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.backtester import Backtester, wilson_interval
from src.execution.mock import MockExecutionHandler
from src.preprocessor import Preprocessor
from src.risk_manager import RiskManager
from src.signal_generator import SignalGenerator


def _candles(rows) -> pd.DataFrame:
    """rows: list of (open, high, low, close, zvol). Hourly index."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [r[0] for r in rows],
            "High": [r[1] for r in rows],
            "Low": [r[2] for r in rows],
            "Close": [r[3] for r in rows],
            "ZScore_Volume": [r[4] for r in rows],
        },
        index=idx,
    )


def _bt(**kw):
    # Explicit so tests don't depend on env-overridable config (shorts, time exit).
    kw.setdefault("use_time_exit", False)
    return Backtester(
        signal_generator=SignalGenerator(volume_threshold=1.5, confidence_threshold=0.55,
                                         allow_shorts=True),
        risk_manager=RiskManager(starting_equity=10_000, risk_fraction=0.01,
                                 stop_loss_pct=0.01, take_profit_pct=0.01),
        execution_handler=MockExecutionHandler(),
        symbol="EURUSD",
        **kw,
    )


# --------------------------------------------------------------------------- #
# No-trade cases (README §8 ranging scenario)
# --------------------------------------------------------------------------- #
def test_ranging_market_no_trades():
    # Low volume Z everywhere -> volume gate never passes -> zero trades.
    df = _candles([(1.10, 1.101, 1.099, 1.10, 0.2)] * 10)
    res = _bt().run(df, probabilities=[0.9] * 10)  # confident, but gate blocks
    assert res.n_trades == 0
    assert res.net_pnl == 0.0


def test_low_confidence_no_trades():
    # High volume but model unsure (0.5) -> ML gate fails -> no trades.
    df = _candles([(1.10, 1.12, 1.08, 1.10, 3.0)] * 10)
    res = _bt().run(df, probabilities=[0.5] * 10)
    assert res.n_trades == 0


# --------------------------------------------------------------------------- #
# Forced win / loss
# --------------------------------------------------------------------------- #
def test_buy_take_profit_is_a_win():
    # Bar 0: entry signal (vol high, prob high) at close 1.10, TP at +1% = 1.111.
    # Bar 1: high reaches 1.12 -> TP hit -> win.
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),   # entry candle
        (1.10, 1.12, 1.10, 1.115, 0.2),  # TP touched
        (1.115, 1.116, 1.114, 1.115, 0.2),
    ])
    res = _bt().run(df, probabilities=[0.9, 0.5, 0.5])
    assert res.n_trades == 1
    assert res.wins == 1
    assert res.net_pnl > 0


def test_buy_stop_loss_is_a_loss():
    # Bar 1 low drops to 1.08 -> SL at -1% = 1.089 hit -> loss.
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),
        (1.10, 1.10, 1.08, 1.085, 0.2),
        (1.085, 1.086, 1.084, 1.085, 0.2),
    ])
    res = _bt().run(df, probabilities=[0.9, 0.5, 0.5])
    assert res.n_trades == 1
    assert res.losses == 1
    assert res.net_pnl < 0


def test_sell_take_profit_is_a_win():
    # Confident bearish (prob 0.1) + high vol -> SELL; price falls to TP.
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),
        (1.10, 1.10, 1.08, 1.085, 0.2),  # low hits SELL TP (-1% = 1.089)
        (1.085, 1.086, 1.084, 1.085, 0.2),
    ])
    res = _bt().run(df, probabilities=[0.1, 0.5, 0.5])
    assert res.n_trades == 1
    assert res.wins == 1


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def test_win_rate_and_profit_factor():
    # One win then one loss -> win_rate 0.5.
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),   # entry 1 (win)
        (1.10, 1.12, 1.10, 1.115, 0.2),  # TP
        (1.115, 1.115, 1.115, 1.115, 2.0),  # entry 2 (loss)
        (1.115, 1.115, 1.10, 1.10, 0.2),    # SL
        (1.10, 1.10, 1.10, 1.10, 0.2),
    ])
    res = _bt().run(df, probabilities=[0.9, 0.5, 0.9, 0.5, 0.5])
    assert res.n_trades == 2
    assert res.win_rate == pytest.approx(0.5)
    assert res.profit_factor > 0


def test_drawdown_is_fraction_between_0_and_1():
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),
        (1.10, 1.10, 1.05, 1.06, 0.2),   # big loss
        (1.06, 1.06, 1.06, 1.06, 0.2),
    ])
    res = _bt().run(df, probabilities=[0.9, 0.5, 0.5])
    assert 0.0 <= res.max_drawdown <= 1.0


def test_meets_targets_structure():
    df = _candles([(1.10, 1.101, 1.099, 1.10, 0.2)] * 5)
    res = _bt().run(df, probabilities=[0.5] * 5)
    targets = res.meets_targets()
    assert set(targets) == {"win_rate", "max_drawdown", "profit_factor", "sharpe"}
    assert all(isinstance(v, bool) for v in targets.values())


def test_probabilities_length_mismatch_raises():
    df = _candles([(1.10, 1.10, 1.10, 1.10, 2.0)] * 3)
    with pytest.raises(ValueError, match="length must match"):
        _bt().run(df, probabilities=[0.9])


def test_result_as_dict_has_all_metrics():
    df = _candles([(1.10, 1.101, 1.099, 1.10, 0.2)] * 5)
    res = _bt().run(df, probabilities=[0.5] * 5)
    d = res.as_dict()
    for k in ["n_trades", "win_rate", "net_pnl", "profit_factor",
              "max_drawdown", "sharpe", "final_equity"]:
        assert k in d


# --------------------------------------------------------------------------- #
# Spread/slippage reduce profit (cost realism)
# --------------------------------------------------------------------------- #
def test_costs_reduce_pnl():
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),
        (1.10, 1.12, 1.10, 1.115, 0.2),
        (1.115, 1.116, 1.114, 1.115, 0.2),
    ])
    probs = [0.9, 0.5, 0.5]

    frictionless = Backtester(
        signal_generator=SignalGenerator(volume_threshold=1.5, confidence_threshold=0.55),
        risk_manager=RiskManager(starting_equity=10_000, risk_fraction=0.01,
                                 stop_loss_pct=0.01, take_profit_pct=0.01),
        execution_handler=MockExecutionHandler(spread=0.0, slippage=0.0),
    ).run(df, probs).net_pnl

    with_costs = Backtester(
        signal_generator=SignalGenerator(volume_threshold=1.5, confidence_threshold=0.55),
        risk_manager=RiskManager(starting_equity=10_000, risk_fraction=0.01,
                                 stop_loss_pct=0.01, take_profit_pct=0.01),
        execution_handler=MockExecutionHandler(spread=0.0005, slippage=0.0005),
    ).run(df, probs).net_pnl

    assert with_costs < frictionless


# --------------------------------------------------------------------------- #
# Win-rate confidence interval (Wilson)
# --------------------------------------------------------------------------- #
def test_wilson_interval_textbook_values():
    lo, hi = wilson_interval(8, 10, z=1.96)
    assert lo == pytest.approx(0.4902, abs=5e-4)
    assert hi == pytest.approx(0.9433, abs=5e-4)
    lo0, hi0 = wilson_interval(0, 10, z=1.96)
    assert lo0 == pytest.approx(0.0, abs=1e-12)
    assert hi0 == pytest.approx(0.2775, abs=5e-4)
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_result_reports_win_rate_interval():
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),
        (1.10, 1.12, 1.10, 1.115, 0.2),
        (1.115, 1.115, 1.115, 1.115, 2.0),
        (1.115, 1.115, 1.10, 1.10, 0.2),
        (1.10, 1.10, 1.10, 1.10, 0.2),
    ])
    res = _bt().run(df, probabilities=[0.9, 0.5, 0.9, 0.5, 0.5])
    assert res.win_rate_ci_low < res.win_rate < res.win_rate_ci_high
    assert (res.win_rate_ci_low, res.win_rate_ci_high) == pytest.approx(wilson_interval(1, 2))
    assert {"win_rate_ci_low", "win_rate_ci_high"} <= set(res.as_dict())


# --------------------------------------------------------------------------- #
# Trade bookkeeping + time exit (label's vertical barrier)
# --------------------------------------------------------------------------- #
def _drift_up(n_after: int = 7) -> pd.DataFrame:
    """Entry candle (high vol) then a slow up-drift that never touches ±1% barriers."""
    rows = [(1.10, 1.10, 1.10, 1.10, 2.0)]
    for k in range(1, n_after + 1):
        c = 1.10 + 0.0005 * k
        rows.append((c, c + 0.001, c - 0.001, c, 0.2))
    return _candles(rows)


def test_sl_tp_trades_record_reason_times_and_bars_held():
    df = _candles([
        (1.10, 1.10, 1.10, 1.10, 2.0),
        (1.10, 1.12, 1.10, 1.115, 0.2),  # TP touched
        (1.115, 1.116, 1.114, 1.115, 0.2),
    ])
    t = _bt().run(df, probabilities=[0.9, 0.5, 0.5]).trades[0]
    assert t["exit_reason"] == "take_profit"
    assert t["entry_time"] == df.index[0]
    assert t["exit_time"] == df.index[1]
    assert t["bars_held"] == 1


def test_time_exit_closes_after_n_bars_at_close():
    df = _drift_up()
    res = _bt(use_time_exit=True, time_exit_bars=3).run(df, [0.9] + [0.5] * 7)
    assert res.n_trades == 1
    t = res.trades[0]
    assert t["exit_reason"] == "time_exit"
    assert t["bars_held"] == 3
    assert t["exit_time"] == df.index[3]
    assert t["exit_price"] == pytest.approx(df["Close"].iloc[3])
    assert res.net_pnl > 0  # closed above entry


def test_without_time_exit_trade_runs_to_end_of_data():
    df = _drift_up()
    t = _bt(use_time_exit=False).run(df, [0.9] + [0.5] * 7).trades[0]
    assert t["exit_reason"] == "end_of_data"
    assert t["bars_held"] == 7


def test_time_exit_default_comes_from_config(monkeypatch):
    monkeypatch.setattr(settings, "USE_TIME_EXIT", True)
    assert Backtester().time_exit_bars == settings.TRIPLE_BARRIER_MAX_HOLD
    monkeypatch.setattr(settings, "USE_TIME_EXIT", False)
    assert Backtester().time_exit_bars is None


def _label_vs_trade(label_dynamic_sl: bool, entry_z: float, use_time_exit: bool):
    """For many entry bars on a random walk, compare the triple-barrier label of
    bar i with the outcome of a frictionless BUY the backtester opens at bar i.

    Barriers are sized (SL 0.8% / TP 0.6% / 4-bar hold) so that time-outs, stop
    hits and target hits all occur — otherwise a missing time exit would go
    unnoticed. Returns (mismatches, trades, wins).
    """
    rng = np.random.default_rng(7)
    n = 400
    close = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    high = close * (1 + np.abs(rng.normal(0, 0.0015, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.0015, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    base = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close,
                         "ZScore_Volume": 0.0}, index=idx)
    sl, tp, hold = 0.008, 0.006, 4
    pre = Preprocessor(label_method="triple_barrier", sl_pct=sl, tp_pct=tp,
                       max_hold=hold, label_dynamic_sl=label_dynamic_sl)

    mismatches = trades = wins = 0
    for i in range(5, n - hold - 1, 9):
        df = base.copy()
        df.iloc[i, df.columns.get_loc("ZScore_Volume")] = entry_z  # only bar i is gated
        label = pre.add_triple_barrier_labels(df)["Target"].iloc[i]
        probs = np.full(n, 0.5)
        probs[i] = 0.9
        res = Backtester(
            signal_generator=SignalGenerator(volume_threshold=1.5,
                                             confidence_threshold=0.55),
            risk_manager=RiskManager(
                starting_equity=10_000, risk_fraction=0.01,
                stop_loss_pct=sl, take_profit_pct=tp,
                dynamic_sl_zscore_trigger=settings.DYNAMIC_SL_ZSCORE_TRIGGER,
                dynamic_sl_tighten_factor=settings.DYNAMIC_SL_TIGHTEN_FACTOR,
            ),
            execution_handler=MockExecutionHandler(),
            use_time_exit=use_time_exit, time_exit_bars=hold,
        ).run(df, probs)
        assert res.n_trades == 1
        won = res.trades[0]["pnl"] > 0
        mismatches += won != (label == 1.0)
        trades += 1
        wins += won
    return mismatches, trades, wins


@pytest.mark.parametrize("label_dynamic_sl, entry_z", [(False, 1.9), (True, 2.5)])
def test_aligned_trade_outcome_matches_triple_barrier_label(label_dynamic_sl, entry_z):
    """With the time exit on (and LABEL_DYNAMIC_SL on when the stop is tightened),
    a frictionless BUY entered at bar i wins iff the triple-barrier label of bar i
    is 1 — i.e. the label describes exactly the trade the backtester takes."""
    mismatches, trades, wins = _label_vs_trade(label_dynamic_sl, entry_z,
                                               use_time_exit=True)
    assert trades >= 30
    assert 0 < wins < trades          # both outcomes exercised
    assert mismatches == 0


@pytest.mark.parametrize(
    "label_dynamic_sl, entry_z, use_time_exit",
    [(False, 2.5, True),    # trade's stop tightened, label's isn't
     (False, 1.9, False)],  # label times out, trade doesn't
)
def test_misaligned_label_and_trade_disagree(label_dynamic_sl, entry_z, use_time_exit):
    """Negative control: the check above must be able to FAIL. Each known
    misalignment produces trades whose outcome contradicts their label."""
    mismatches, _, _ = _label_vs_trade(label_dynamic_sl, entry_z, use_time_exit)
    assert mismatches > 0
