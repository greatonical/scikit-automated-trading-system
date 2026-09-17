"""Tests for Preprocessor (Module 2).

The load-bearing tests here are the anti-leakage ones (README §5/§6):
  * Z-Score features are TRAILING (backward-looking only).
  * Labels are FORWARD-looking and never leak into features.
  * The train/test split is chronological with no shuffle and no overlap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.preprocessor import Preprocessor


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _ohlcv(periods: int = 200, seed: int = 0) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=periods, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 1.10 + np.cumsum(rng.normal(0, 0.001, periods))
    return pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.0001, periods),
            "High": close + np.abs(rng.normal(0, 0.0002, periods)),
            "Low": close - np.abs(rng.normal(0, 0.0002, periods)),
            "Close": close,
            "Volume": rng.integers(1000, 5000, periods).astype(float),
        },
        index=idx,
    )


@pytest.fixture
def pre():
    # Most existing tests assume the simple next-candle label + base features;
    # the triple-barrier and indicator tests use their own setups. Pinning the
    # feature list isolates these tests from whatever indicators are toggled on
    # by default in config (B1–B4 experiments flip those defaults around).
    from config import settings
    return Preprocessor(
        zscore_window=10, label_horizon=1, split_ratio=0.8,
        label_method="next_candle",
        feature_columns=list(settings.BASE_FEATURE_COLUMNS),
    )


# --------------------------------------------------------------------------- #
# Z-Score correctness + trailing property (NO lookahead)
# --------------------------------------------------------------------------- #
def test_zscore_matches_manual_trailing_calc(pre):
    df = _ohlcv(50)
    out = pre.add_zscores(df)
    w = pre.zscore_window
    # Pick a row well past the window and compute Z by hand from the trailing window.
    t = 30
    window = df["Close"].iloc[t - w + 1 : t + 1]
    expected = (df["Close"].iloc[t] - window.mean()) / window.std(ddof=1)
    assert out["ZScore_Close"].iloc[t] == pytest.approx(expected, rel=1e-9)


def test_zscore_is_strictly_trailing_no_lookahead(pre):
    """Z-Score at row t must not change if future rows are removed."""
    df = _ohlcv(80)
    full = pre.add_zscores(df)
    t = 40
    # Recompute using only data up to and including row t.
    truncated = pre.add_zscores(df.iloc[: t + 1])
    assert full["ZScore_Close"].iloc[t] == pytest.approx(
        truncated["ZScore_Close"].iloc[t], rel=1e-12, nan_ok=True
    )
    assert full["ZScore_Volume"].iloc[t] == pytest.approx(
        truncated["ZScore_Volume"].iloc[t], rel=1e-12, nan_ok=True
    )


def test_zscore_leading_rows_are_nan_until_window_filled(pre):
    df = _ohlcv(30)
    out = pre.add_zscores(df)
    w = pre.zscore_window
    # First (w-1) rows lack a full window -> NaN.
    assert out["ZScore_Close"].iloc[: w - 1].isna().all()
    assert out["ZScore_Close"].iloc[w - 1 :].notna().any()


def test_zscore_flat_series_is_zero_not_inf():
    pre = Preprocessor(zscore_window=5)
    idx = pd.date_range("2023-01-01", periods=10, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 100.0,
        },
        index=idx,
    )
    out = pre.add_zscores(df)
    # No deviation anywhere -> zeros, never inf/NaN past the window.
    tail = out["ZScore_Close"].iloc[5:]
    assert np.isfinite(tail).all()
    assert (tail == 0.0).all()


# --------------------------------------------------------------------------- #
# Labels are forward-looking
# --------------------------------------------------------------------------- #
def test_label_is_forward_bullish(pre):
    idx = pd.date_range("2023-01-01", periods=5, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [1, 1, 1, 1, 1.0],
            "High": [1, 1, 1, 1, 1.0],
            "Low": [1, 1, 1, 1, 1.0],
            "Close": [1.0, 2.0, 1.5, 1.5, 3.0],  # up, down, flat, up
            "Volume": [1, 1, 1, 1, 1.0],
        },
        index=idx,
    )
    out = pre.add_labels(df)
    # row0: next(2.0)>1.0 -> 1 ; row1: next(1.5)<2.0 -> 0 ;
    # row2: next(1.5)==1.5 -> 0 ; row3: next(3.0)>1.5 -> 1 ; row4: no future -> NaN
    assert out["Target"].iloc[0] == 1.0
    assert out["Target"].iloc[1] == 0.0
    assert out["Target"].iloc[2] == 0.0
    assert out["Target"].iloc[3] == 1.0
    assert np.isnan(out["Target"].iloc[4])


def test_target_not_in_feature_columns(pre):
    assert "Target" not in pre.feature_columns


# --------------------------------------------------------------------------- #
# Triple-barrier labels (Step A)
# --------------------------------------------------------------------------- #
def _tb_pre(**kw):
    defaults = dict(
        zscore_window=3, label_method="triple_barrier",
        tp_pct=0.01, sl_pct=0.01, max_hold=5, label_dynamic_sl=False,
    )
    defaults.update(kw)
    return Preprocessor(**defaults)


def _candles(rows):
    """rows: list of (high, low, close). Open = close for simplicity."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [r[2] for r in rows],
            "High": [r[0] for r in rows],
            "Low": [r[1] for r in rows],
            "Close": [r[2] for r in rows],
            "Volume": [1000.0] * len(rows),
        },
        index=idx,
    )


def test_triple_barrier_take_profit_first_is_win():
    pre = _tb_pre()
    # entry 1.00 -> TP=1.01, SL=0.99. Next bar high reaches 1.02 (TP hit) -> 1.
    df = _candles([
        (1.00, 1.00, 1.00),   # entry
        (1.02, 1.00, 1.01),   # high 1.02 >= TP 1.01 -> WIN
        (1.01, 1.00, 1.005),
    ])
    out = pre.add_triple_barrier_labels(df)
    assert out["Target"].iloc[0] == 1.0


def test_triple_barrier_stop_loss_first_is_loss():
    pre = _tb_pre()
    # entry 1.00 -> SL=0.99. Next bar low reaches 0.98 (SL hit) -> 0.
    df = _candles([
        (1.00, 1.00, 1.00),
        (1.005, 0.98, 0.985),  # low 0.98 <= SL 0.99 -> LOSS
        (0.99, 0.98, 0.985),
    ])
    out = pre.add_triple_barrier_labels(df)
    assert out["Target"].iloc[0] == 0.0


def test_triple_barrier_both_same_bar_is_loss():
    pre = _tb_pre()
    # A bar spanning both TP and SL -> conservative LOSS.
    df = _candles([
        (1.00, 1.00, 1.00),
        (1.03, 0.97, 1.00),   # high>=TP AND low<=SL same bar -> 0
        (1.00, 1.00, 1.00),
    ])
    out = pre.add_triple_barrier_labels(df)
    assert out["Target"].iloc[0] == 0.0


def test_triple_barrier_timeout_labels_by_final_close():
    pre = _tb_pre(max_hold=2)
    # Neither barrier hit within 2 bars; final close > entry -> 1.
    df = _candles([
        (1.00, 1.00, 1.00),    # entry
        (1.004, 0.997, 1.002), # no hit
        (1.006, 0.998, 1.005), # no hit; close 1.005 > 1.00 -> WIN by timeout
        (1.005, 1.005, 1.005),
    ])
    out = pre.add_triple_barrier_labels(df)
    assert out["Target"].iloc[0] == 1.0


def test_triple_barrier_labels_are_binary_and_forward():
    pre = _tb_pre()
    df = _candles([(1.0 + 0.001 * i, 1.0 - 0.001 * i, 1.0) for i in range(20)])
    out = pre.add_triple_barrier_labels(df)
    valid = out["Target"].dropna()
    assert set(valid.unique()).issubset({0.0, 1.0})
    # last row has no future bar -> NaN
    assert np.isnan(out["Target"].iloc[-1])


def test_label_method_routes_through_add_labels():
    tb = Preprocessor(label_method="triple_barrier", tp_pct=0.01, sl_pct=0.01,
                      max_hold=3, zscore_window=3)
    nc = Preprocessor(label_method="next_candle", zscore_window=3)
    df = _candles([
        (1.00, 1.00, 1.00),
        (1.02, 1.00, 1.01),
        (1.01, 1.00, 1.005),
        (1.01, 1.00, 1.008),
    ])
    # triple_barrier label for row 0 = win (TP hit); next_candle = up (1.01>1.00).
    assert tb.add_labels(df)["Target"].iloc[0] == 1.0
    assert nc.add_labels(df)["Target"].iloc[0] == 1.0


def test_invalid_label_method_raises():
    with pytest.raises(ValueError, match="label_method"):
        Preprocessor(label_method="bogus")


# --------------------------------------------------------------------------- #
# Label ↔ trade alignment: dynamic stop in the label (LABEL_DYNAMIC_SL)
# --------------------------------------------------------------------------- #
def _tight_stop_candles(entry_z: float) -> pd.DataFrame:
    # entry 1.00: base SL 1% = 0.99, tightened SL 0.5% = 0.995, TP 1% = 1.01.
    # Bar 1 dips to 0.993 (only the tightened stop); bar 2 reaches TP.
    df = _candles([
        (1.00, 1.00, 1.00),
        (1.004, 0.993, 1.000),
        (1.020, 1.000, 1.015),
        (1.000, 1.000, 1.000),
    ])
    df["ZScore_Volume"] = [entry_z, 0.0, 0.0, 0.0]
    return df


def test_label_dynamic_sl_tightens_stop_like_riskmanager():
    df = _tight_stop_candles(entry_z=2.5)   # |z| >= 2.0 trigger -> stop halved
    static = _tb_pre(label_dynamic_sl=False).add_triple_barrier_labels(df)
    dynamic = _tb_pre(label_dynamic_sl=True).add_triple_barrier_labels(df)
    assert static["Target"].iloc[0] == 1.0    # 0.99 stop survives the dip, TP hit
    assert dynamic["Target"].iloc[0] == 0.0   # 0.995 stop is hit first


def test_label_dynamic_sl_below_trigger_matches_static():
    df = _tight_stop_candles(entry_z=1.8)   # below the trigger -> no tightening
    static = _tb_pre(label_dynamic_sl=False).add_triple_barrier_labels(df)
    dynamic = _tb_pre(label_dynamic_sl=True).add_triple_barrier_labels(df)
    pd.testing.assert_series_equal(static["Target"], dynamic["Target"])


def test_label_dynamic_sl_requires_volume_zscore():
    df = _candles([(1.0, 1.0, 1.0), (1.02, 1.0, 1.01)])
    with pytest.raises(KeyError, match="ZScore_Volume"):
        _tb_pre(label_dynamic_sl=True).add_triple_barrier_labels(df)


def test_transform_with_label_dynamic_sl_runs():
    # transform computes Z-Scores before labels, so the dynamic label works end-to-end.
    pre = Preprocessor(zscore_window=10, label_method="triple_barrier",
                       label_dynamic_sl=True,
                       feature_columns=list(settings.BASE_FEATURE_COLUMNS))
    out = pre.transform(_ohlcv(200))
    assert set(out["Target"].unique()).issubset({0.0, 1.0})


# --------------------------------------------------------------------------- #
# Time-of-day features use UTC hours (Step D)
# --------------------------------------------------------------------------- #
def test_time_features_use_utc_hours(monkeypatch):
    monkeypatch.setattr(settings, "USE_TIME_FEATURES", True)
    # Summer (BST = UTC+1): 12:00 London = 11:00 UTC (outside the 12–16 UTC
    # overlap), 13:00 London = 12:00 UTC (inside).
    idx = pd.DatetimeIndex(["2024-07-01 12:00", "2024-07-01 13:00"]).tz_localize(
        "Europe/London"
    )
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                       "Volume": 1.0}, index=idx)
    out = Preprocessor().add_indicators(df)
    assert list(out["SessionOverlap"]) == [0.0, 1.0]


# --------------------------------------------------------------------------- #
# RSI feature (Step B1) — backward-looking, bounded 0–100
# --------------------------------------------------------------------------- #
def test_rsi_in_range_0_100(pre):
    df = _ohlcv(100)
    rsi = pre._rsi(df["Close"], period=14)
    valid = rsi.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_rsi_all_gains_is_100(pre):
    # Strictly rising closes -> no losses -> RSI 100.
    idx = pd.date_range("2024-01-01", periods=30, freq="1h", tz="UTC")
    close = pd.Series(np.arange(1.0, 31.0), index=idx)
    rsi = pre._rsi(close, period=14).dropna()
    assert (rsi == 100.0).all()


def test_rsi_is_trailing_no_lookahead(pre):
    df = _ohlcv(80)
    full = pre._rsi(df["Close"], 14)
    t = 50
    truncated = pre._rsi(df["Close"].iloc[: t + 1], 14)
    assert full.iloc[t] == pytest.approx(truncated.iloc[t], rel=1e-9, nan_ok=True)


def test_add_indicators_appends_rsi_when_enabled(pre, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_RSI", True)
    df = _ohlcv(60)
    out = pre.add_indicators(df)
    assert "RSI" in out.columns


def test_transform_includes_rsi_when_in_features(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_RSI", True)
    pre = Preprocessor(
        zscore_window=10, label_method="next_candle",
        feature_columns=settings.BASE_FEATURE_COLUMNS + ["RSI"],
    )
    out = pre.transform(_ohlcv(200))
    assert "RSI" in out.columns
    assert not out["RSI"].isna().any()


# --------------------------------------------------------------------------- #
# MACD feature (Step B2) — backward-looking
# --------------------------------------------------------------------------- #
def test_macd_histogram_equals_macd_minus_signal(pre):
    df = _ohlcv(120)
    macd, signal, hist = pre._macd(df["Close"], 12, 26, 9)
    pd.testing.assert_series_equal(hist, macd - signal, check_names=False)


def test_macd_is_trailing_no_lookahead(pre):
    df = _ohlcv(120)
    macd_full, _, _ = pre._macd(df["Close"], 12, 26, 9)
    t = 80
    macd_trunc, _, _ = pre._macd(df["Close"].iloc[: t + 1], 12, 26, 9)
    assert macd_full.iloc[t] == pytest.approx(macd_trunc.iloc[t], rel=1e-9)


def test_add_indicators_appends_macd_when_enabled(pre, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_MACD", True)
    out = pre.add_indicators(_ohlcv(80))
    for col in ["MACD", "MACD_Signal", "MACD_Hist"]:
        assert col in out.columns


def test_transform_includes_macd_when_in_features(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_MACD", True)
    pre = Preprocessor(
        zscore_window=10, label_method="next_candle",
        feature_columns=settings.BASE_FEATURE_COLUMNS + ["MACD", "MACD_Signal", "MACD_Hist"],
    )
    out = pre.transform(_ohlcv(200))
    for col in ["MACD", "MACD_Signal", "MACD_Hist"]:
        assert col in out.columns
        assert not out[col].isna().any()


# --------------------------------------------------------------------------- #
# ATR feature (Step B3) — volatility, non-negative, backward-looking
# --------------------------------------------------------------------------- #
def test_atr_is_non_negative(pre):
    df = _ohlcv(100)
    atr = pre._atr(df["High"], df["Low"], df["Close"], 14).dropna()
    assert (atr >= 0).all()


def test_atr_larger_when_ranges_wider(pre):
    # Wide-range candles -> higher ATR than narrow-range candles.
    idx = pd.date_range("2024-01-01", periods=40, freq="1h", tz="UTC")
    narrow = pd.DataFrame({"High": 1.001, "Low": 0.999, "Close": 1.0}, index=idx)
    wide = pd.DataFrame({"High": 1.05, "Low": 0.95, "Close": 1.0}, index=idx)
    a_narrow = pre._atr(narrow["High"], narrow["Low"], narrow["Close"], 14).iloc[-1]
    a_wide = pre._atr(wide["High"], wide["Low"], wide["Close"], 14).iloc[-1]
    assert a_wide > a_narrow


def test_atr_is_trailing_no_lookahead(pre):
    df = _ohlcv(100)
    full = pre._atr(df["High"], df["Low"], df["Close"], 14)
    t = 60
    trunc = pre._atr(
        df["High"].iloc[: t + 1], df["Low"].iloc[: t + 1], df["Close"].iloc[: t + 1], 14
    )
    assert full.iloc[t] == pytest.approx(trunc.iloc[t], rel=1e-9, nan_ok=True)


def test_add_indicators_appends_atr_when_enabled(pre, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_ATR", True)
    out = pre.add_indicators(_ohlcv(80))
    assert "ATR" in out.columns


# --------------------------------------------------------------------------- #
# Order blocks (Step F) — zone detection, strictly causal
# --------------------------------------------------------------------------- #
def _ob(pre, df, **kw):
    # dist_cap is deliberately wider than the real 2% here, so these fixtures
    # exercise the true distance rather than the clip.
    defaults = dict(lookback=3, max_atr_multiple=10.0, min_size_pct=0.0,
                    max_age=100, dist_cap=0.05)
    defaults.update(kw)
    atr = pre._atr(df["High"], df["Low"], df["Close"], 3)
    return pre._order_blocks(
        df["High"].to_numpy(), df["Low"].to_numpy(), df["Close"].to_numpy(),
        atr.to_numpy(), **defaults,
    )


def _ohlc(rows) -> pd.DataFrame:
    """rows: list of (high, low, close)."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(
        {"Open": [r[2] for r in rows], "High": [r[0] for r in rows],
         "Low": [r[1] for r in rows], "Close": [r[2] for r in rows],
         "Volume": [1000.0] * len(rows)},
        index=idx,
    )


def _break_out_sequence():
    """Four flat bars, a dip, then a candle closing above the swing high."""
    return _ohlc([
        (1.010, 1.000, 1.005),
        (1.010, 1.000, 1.005),
        (1.010, 1.000, 1.005),
        (1.004, 0.990, 0.995),   # the dip — lowest low, becomes the zone
        (1.030, 1.000, 1.025),   # closes above the swing high -> bullish break
        (1.030, 1.020, 1.025),
        (1.030, 1.020, 1.025),
    ])


def test_order_block_forms_on_a_close_beyond_the_swing(pre):
    df = _break_out_sequence()
    bull, _, inside = _ob(pre, df)
    # No zone exists until the break candle has closed...
    assert bull[4] == pytest.approx(0.05)          # cap = "nothing nearby"
    # ...and from the next bar the dip candle (high 1.004) is the zone below price.
    assert bull[5] == pytest.approx((1.025 - 1.004) / 1.025, rel=1e-6)
    assert inside[5] == 0.0                        # price is above the zone, not in it


def test_order_block_is_consumed_once_price_returns_into_it(pre):
    rows = _break_out_sequence().values.tolist()
    df = _ohlc([(r[1], r[2], r[3]) for r in rows] + [
        (1.030, 1.000, 1.002),   # trades back into the zone -> mitigated
        (1.030, 1.020, 1.025),
    ])
    bull, _, _ = _ob(pre, df)
    assert bull[-1] == pytest.approx(0.05)         # zone gone, so "nothing nearby"


def test_oversized_zone_is_rejected(pre):
    df = _break_out_sequence()
    # An ATR multiple of ~0 rejects every candidate zone.
    bull, _, _ = _ob(pre, df, max_atr_multiple=0.01)
    assert bull[5] == pytest.approx(0.05)


def test_distance_feature_is_clipped(pre):
    """The real config caps the distance at ±2% so one far-away zone can't dominate."""
    df = _break_out_sequence()
    bull, _, _ = _ob(pre, df, dist_cap=0.001)
    assert bull[5] == pytest.approx(0.001)


def test_order_block_features_are_trailing_no_lookahead(pre):
    df = _ohlc([(1.0 + 0.004 * np.sin(i / 3), 1.0 - 0.004 * np.sin(i / 3),
                 1.0 + 0.002 * np.sin(i / 2)) for i in range(120)])
    full = _ob(pre, df)
    t = 80
    trunc = _ob(pre, df.iloc[: t + 1])
    for f, tr in zip(full, trunc):
        assert f[t] == pytest.approx(tr[t], rel=1e-12, nan_ok=True)


def test_add_indicators_appends_order_blocks_when_enabled(pre, monkeypatch):
    monkeypatch.setattr(settings, "USE_ORDER_BLOCKS", True)
    out = pre.add_indicators(_ohlcv(120))
    for col in ["OB_BullDist", "OB_BearDist", "OB_Inside"]:
        assert col in out.columns


def test_transform_includes_order_blocks_when_in_features(monkeypatch):
    monkeypatch.setattr(settings, "USE_ORDER_BLOCKS", True)
    pre = Preprocessor(
        zscore_window=10, label_method="next_candle",
        feature_columns=settings.BASE_FEATURE_COLUMNS
        + ["OB_BullDist", "OB_BearDist", "OB_Inside"],
    )
    out = pre.transform(_ohlcv(300))
    for col in ["OB_BullDist", "OB_BearDist", "OB_Inside"]:
        assert not out[col].isna().any()
    assert set(out["OB_Inside"].unique()).issubset({-1.0, 0.0, 1.0})


# --------------------------------------------------------------------------- #
# Higher-timeframe trend feature (Step B4) — backward-looking
# --------------------------------------------------------------------------- #
def test_htf_trend_up_flag_matches_ma(pre):
    idx = pd.date_range("2024-01-01", periods=30, freq="1h", tz="UTC")
    # Strictly rising -> price above its trailing MA -> TrendUp 1 once MA defined.
    close = pd.Series(np.arange(1.0, 31.0), index=idx)
    dist, up = pre._htf_trend(close, window=10)
    valid = up.dropna()
    assert (valid == 1.0).all()
    # distance is positive in an uptrend
    assert (dist.dropna() > 0).all()


def test_htf_trend_is_trailing_no_lookahead(pre):
    df = _ohlcv(150)
    dist_full, up_full = pre._htf_trend(df["Close"], 50)
    t = 100
    dist_tr, up_tr = pre._htf_trend(df["Close"].iloc[: t + 1], 50)
    assert dist_full.iloc[t] == pytest.approx(dist_tr.iloc[t], rel=1e-9, nan_ok=True)


def test_add_indicators_appends_trend_when_enabled(pre, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "USE_HTF_TREND", True)
    monkeypatch.setattr(settings, "HTF_TREND_WINDOW", 20)
    out = pre.add_indicators(_ohlcv(80))
    assert "TrendDist" in out.columns and "TrendUp" in out.columns


# --------------------------------------------------------------------------- #
# Transform drops unusable rows and yields the right schema
# --------------------------------------------------------------------------- #
def test_transform_schema_and_no_nans(pre):
    df = _ohlcv(120)
    out = pre.transform(df)
    for col in settings.FEATURE_COLUMNS + ["Target"]:
        assert col in out.columns
    # No NaNs survive in the model-facing columns.
    assert not out[settings.FEATURE_COLUMNS + ["Target"]].isna().any().any()
    # Target is binary.
    assert set(out["Target"].unique()).issubset({0.0, 1.0})


def test_features_and_labels_split(pre):
    df = _ohlcv(120)
    out = pre.transform(df)
    X, y = pre.features_and_labels(out)
    assert list(X.columns) == pre.feature_columns
    assert "Target" not in X.columns
    assert set(y.unique()).issubset({0, 1})
    assert len(X) == len(y)


# --------------------------------------------------------------------------- #
# Chronological split — no shuffle, no overlap, correct boundary
# --------------------------------------------------------------------------- #
def test_chronological_split_ratio_and_order(pre):
    df = _ohlcv(100)
    out = pre.transform(df)
    train, test = pre.chronological_split(out)

    # ~80/20 by row count
    assert len(train) == int(len(out) * 0.8)
    assert len(train) + len(test) == len(out)

    # every train timestamp is strictly before every test timestamp
    assert train.index.max() < test.index.min()

    # both sides individually time-ordered
    assert train.index.is_monotonic_increasing
    assert test.index.is_monotonic_increasing


def test_split_does_not_shuffle(pre):
    """The concatenation of train+test must equal the original ordering."""
    df = _ohlcv(60)
    out = pre.transform(df)
    train, test = pre.chronological_split(out)
    recombined = pd.concat([train, test])
    pd.testing.assert_index_equal(recombined.index, out.index)


def test_prepare_end_to_end(pre):
    df = _ohlcv(150)
    X_train, y_train, X_test, y_test = pre.prepare(df)
    assert len(X_train) == len(y_train)
    assert len(X_test) == len(y_test)
    assert X_train.index.max() < X_test.index.min()  # no temporal leakage
    assert list(X_train.columns) == pre.feature_columns


def test_invalid_split_ratio_raises():
    with pytest.raises(ValueError):
        Preprocessor(split_ratio=1.5)
    with pytest.raises(ValueError):
        Preprocessor(split_ratio=0.0)


def test_empty_input_passthrough(pre):
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    assert pre.transform(empty).empty
    a, b = pre.chronological_split(empty)
    assert a.empty and b.empty
