"""Tests for RiskManager (Module 5 / README §7).

Covers: fixed-fractional sizing, dynamic (tightening) stop-loss, correct
stop/target placement per side, and the hard limits (drawdown + daily loss).
"""
from __future__ import annotations

import pytest

from src.risk_manager import RiskManager, TradePlan, dynamic_stop_pct


@pytest.fixture
def rm():
    return RiskManager(
        starting_equity=10_000,
        risk_fraction=0.01,            # risk 1% = $100 per trade
        stop_loss_pct=0.005,           # 0.5%
        take_profit_pct=0.010,         # 1.0%
        max_drawdown_limit=0.15,
        daily_loss_limit=0.05,
        dynamic_sl_zscore_trigger=2.0,
        dynamic_sl_tighten_factor=0.5,
    )


# --------------------------------------------------------------------------- #
# Fixed-fractional position sizing
# --------------------------------------------------------------------------- #
def test_risk_amount_is_fraction_of_equity(rm):
    plan = rm.size_position("BUY", entry_price=1.10)
    assert plan.risk_amount == pytest.approx(100.0)  # 1% of 10_000


def test_volume_matches_risk_over_stop_distance(rm):
    entry = 1.10
    plan = rm.size_position("BUY", entry_price=entry)
    # per-unit risk = entry * sl_pct; volume = risk_amount / per-unit risk
    per_unit = entry * 0.005
    assert plan.volume == pytest.approx(100.0 / per_unit)


def test_sizing_scales_down_as_equity_falls(rm):
    big = rm.size_position("BUY", 1.10).risk_amount
    rm.update_equity(5_000)            # equity halved
    small = rm.size_position("BUY", 1.10).risk_amount
    assert small == pytest.approx(big / 2)


# --------------------------------------------------------------------------- #
# Stop / target placement per side
# --------------------------------------------------------------------------- #
def test_buy_stop_below_target_above(rm):
    plan = rm.size_position("BUY", entry_price=1.10)
    assert plan.stop_loss < 1.10 < plan.take_profit
    assert plan.stop_loss == pytest.approx(1.10 * (1 - 0.005))
    assert plan.take_profit == pytest.approx(1.10 * (1 + 0.010))


def test_sell_stop_above_target_below(rm):
    plan = rm.size_position("SELL", entry_price=1.10)
    assert plan.take_profit < 1.10 < plan.stop_loss
    assert plan.stop_loss == pytest.approx(1.10 * (1 + 0.005))
    assert plan.take_profit == pytest.approx(1.10 * (1 - 0.010))


def test_invalid_side_raises(rm):
    with pytest.raises(ValueError):
        rm.size_position("HOLD", 1.10)


def test_invalid_price_raises(rm):
    with pytest.raises(ValueError):
        rm.size_position("BUY", -1.0)


# --------------------------------------------------------------------------- #
# Dynamic stop-loss (tightens on volatility spike)
# --------------------------------------------------------------------------- #
def test_stop_normal_when_zscore_below_trigger(rm):
    assert rm.stop_distance_pct(volume_zscore=1.0) == pytest.approx(0.005)


def test_stop_tightens_when_zscore_exceeds_trigger(rm):
    # |z| = 2.5 >= 2.0 trigger -> 0.005 * 0.5 = 0.0025
    assert rm.stop_distance_pct(volume_zscore=2.5) == pytest.approx(0.0025)


def test_shared_dynamic_stop_rule_matches_method(rm):
    # The label (LABEL_DYNAMIC_SL) uses this same helper, so they can't diverge.
    for z in (0.0, 1.9, 2.0, -2.5, 3.0):
        assert rm.stop_distance_pct(z) == dynamic_stop_pct(0.005, z, 2.0, 0.5)


def test_dynamic_stop_trigger_is_inclusive():
    assert dynamic_stop_pct(0.01, 2.0, 2.0, 0.5) == pytest.approx(0.005)
    assert dynamic_stop_pct(0.01, 1.99, 2.0, 0.5) == pytest.approx(0.01)


def test_tightened_stop_is_closer_to_entry(rm):
    normal = rm.size_position("BUY", 1.10, volume_zscore=0.0)
    tight = rm.size_position("BUY", 1.10, volume_zscore=3.0)
    # tighter stop sits closer to entry
    assert tight.stop_loss > normal.stop_loss
    # and a closer stop -> larger position for the same fixed risk
    assert tight.volume > normal.volume


# --------------------------------------------------------------------------- #
# Hard limits
# --------------------------------------------------------------------------- #
def test_can_trade_true_at_start(rm):
    assert rm.can_trade() is True


def test_drawdown_limit_halts_trading(rm):
    rm.update_equity(10_000)           # peak
    rm.update_equity(8_400)            # 16% below peak >= 15% limit
    assert rm.current_drawdown() == pytest.approx(0.16)
    assert rm.can_trade() is False


def test_below_drawdown_limit_allows_trading(rm):
    rm.update_equity(10_000)
    rm.update_equity(9_000)            # 10% below peak < 15% drawdown limit
    rm.start_new_day()                 # isolate drawdown from the daily-loss check
    assert rm.can_trade() is True


def test_daily_loss_limit_halts_trading(rm):
    rm.start_new_day()                 # baseline 10_000
    rm.update_equity(9_400)            # 6% daily loss >= 5% limit
    assert rm.daily_loss() == pytest.approx(0.06)
    assert rm.can_trade() is False


def test_new_day_resets_daily_loss(rm):
    rm.start_new_day()
    rm.update_equity(9_600)            # 4% loss, still ok
    assert rm.can_trade() is True
    rm.start_new_day()                 # new baseline = 9_600
    assert rm.daily_loss() == pytest.approx(0.0)


def test_peak_tracks_highest_equity(rm):
    rm.update_equity(11_000)
    rm.update_equity(10_500)
    assert rm.peak_equity == 11_000
    assert rm.current_drawdown() == pytest.approx((11_000 - 10_500) / 11_000)


def test_returns_tradeplan_type(rm):
    assert isinstance(rm.size_position("BUY", 1.10), TradePlan)


# --------------------------------------------------------------------------- #
# ATR-based stops (Step B3 — off by default, but the code path is covered)
# --------------------------------------------------------------------------- #
def test_atr_stops_used_when_enabled(rm, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_ATR_STOPS", True)
    monkeypatch.setattr(settings, "ATR_SL_MULTIPLE", 2.0)
    monkeypatch.setattr(settings, "ATR_TP_MULTIPLE", 4.0)
    atr = 0.001
    plan = rm.size_position("BUY", entry_price=1.10, atr=atr)
    # SL distance = atr*2 = 0.002 below; TP distance = atr*4 = 0.004 above.
    assert plan.stop_loss == pytest.approx(1.10 - 0.002)
    assert plan.take_profit == pytest.approx(1.10 + 0.004)


def test_atr_stops_ignored_when_no_atr(rm, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_ATR_STOPS", True)
    # No atr passed -> falls back to flat-% stops.
    plan = rm.size_position("BUY", entry_price=1.10, atr=None)
    assert plan.stop_loss == pytest.approx(1.10 * (1 - 0.005))
