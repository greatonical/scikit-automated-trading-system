"""Tests for DataHandler (Module 1).

All tests mock the yfinance download so they run offline and deterministically.
A single optional test (marked `network`) does a real fetch and is skipped by
default — run with `pytest -m network` to exercise the live Yahoo path.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.data_handler import OHLCV_COLUMNS, DataHandler


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
def _make_raw_1h(periods: int = 48, *, multiindex: bool = True) -> pd.DataFrame:
    """Build a yfinance-shaped 1h OHLCV frame for EURUSD."""
    idx = pd.date_range("2024-01-01", periods=periods, freq="1h", tz="UTC")
    rng = np.random.default_rng(0)
    close = 1.10 + np.cumsum(rng.normal(0, 0.0005, periods))
    data = {
        "Open": close + rng.normal(0, 0.0001, periods),
        "High": close + np.abs(rng.normal(0, 0.0003, periods)),
        "Low": close - np.abs(rng.normal(0, 0.0003, periods)),
        "Close": close,
        "Volume": rng.integers(1000, 5000, periods).astype(float),
    }
    df = pd.DataFrame(data, index=idx)
    if multiindex:
        # mimic yfinance single-ticker MultiIndex columns: (field, ticker)
        df.columns = pd.MultiIndex.from_product([df.columns, ["EURUSD=X"]])
    return df


@pytest.fixture
def handler(tmp_path):
    """A DataHandler writing to a temp cache dir.

    Futures-volume merge is OFF by default here so the existing price/clean/cache
    tests stay focused on one ticker. The merge has its own dedicated tests.
    """
    return DataHandler(
        cache_dir=tmp_path, cache_enabled=True, use_futures_volume=False
    )


def _patch_download(handler: DataHandler, frame: pd.DataFrame) -> None:
    """Force _download to return a fixed frame (no network), any ticker."""
    handler._download = lambda ticker, start, end, interval: frame  # type: ignore[method-assign]


def _make_futures_vol(periods: int = 24, base: int = 100, *, multiindex: bool = True):
    """A futures-shaped OHLCV frame whose Volume is the row index * base."""
    idx = pd.date_range("2024-01-01", periods=periods, freq="1h", tz="UTC")
    vol = (np.arange(periods) + 1) * base
    df = pd.DataFrame(
        {
            "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
            "Volume": vol.astype(float),
        },
        index=idx,
    )
    if multiindex:
        df.columns = pd.MultiIndex.from_product([df.columns, ["6E=F"]])
    return df


# --------------------------------------------------------------------------- #
# Column normalisation
# --------------------------------------------------------------------------- #
def test_normalise_flattens_multiindex(handler):
    raw = _make_raw_1h(multiindex=True)
    out = handler._normalise_columns(raw)
    assert list(out.columns) == OHLCV_COLUMNS
    assert not isinstance(out.columns, pd.MultiIndex)


def test_normalise_handles_flat_columns(handler):
    raw = _make_raw_1h(multiindex=False)
    out = handler._normalise_columns(raw)
    assert list(out.columns) == OHLCV_COLUMNS


def test_normalise_empty_returns_ohlcv_schema(handler):
    out = handler._normalise_columns(pd.DataFrame())
    assert list(out.columns) == OHLCV_COLUMNS
    assert out.empty


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #
def test_clean_sorts_dedupes_and_fills(handler):
    idx = pd.to_datetime(
        ["2024-01-01 02:00", "2024-01-01 00:00", "2024-01-01 00:00", "2024-01-01 01:00"],
        utc=True,
    )
    df = pd.DataFrame(
        {
            "Open": [1, 1, 1, 1.0],
            "High": [1, 1, 1, 1.0],
            "Low": [1, 1, 1, 1.0],
            "Close": [3.0, 1.0, 1.0, np.nan],
            "Volume": [10, 10, 10, np.nan],
        },
        index=idx,
    )
    out = handler._clean(df)
    # sorted ascending
    assert out.index.is_monotonic_increasing
    # duplicate 00:00 collapsed to one
    assert out.index.duplicated().sum() == 0
    # the row whose Close was NaN got forward-filled (not dropped) since ffill runs
    assert out["Close"].isna().sum() == 0
    # Volume NaN -> 0
    assert (out["Volume"] >= 0).all()
    # tz-aware
    assert out.index.tz is not None


def test_clean_empty_passthrough(handler):
    assert handler._clean(pd.DataFrame()).empty


# --------------------------------------------------------------------------- #
# Resampling 1h -> 4h
# --------------------------------------------------------------------------- #
def test_resample_1h_to_4h_ohlc_correct(handler):
    idx = pd.date_range("2024-01-01 00:00", periods=8, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": [10, 11, 12, 13, 20, 21, 22, 23.0],
            "High": [15, 16, 17, 18, 25, 26, 27, 28.0],
            "Low": [5, 6, 7, 8, 15, 16, 17, 18.0],
            "Close": [11, 12, 13, 14, 21, 22, 23, 24.0],
            "Volume": [1, 1, 1, 1, 2, 2, 2, 2.0],
        },
        index=idx,
    )
    out = handler._resample(df, "4h")
    assert len(out) == 2
    first = out.iloc[0]
    assert first["Open"] == 10        # first of bucket
    assert first["High"] == 18        # max of bucket
    assert first["Low"] == 5          # min of bucket
    assert first["Close"] == 14       # last of bucket
    assert first["Volume"] == 4       # sum of bucket
    second = out.iloc[1]
    assert second["Open"] == 20
    assert second["Close"] == 24
    assert second["Volume"] == 8


# --------------------------------------------------------------------------- #
# Intraday window clamping (Yahoo's ~730-day limit)
# --------------------------------------------------------------------------- #
def test_intraday_window_clamped_to_max_days(handler):
    start, end = handler._resolve_window("1h")
    span_days = (end - start).days
    assert span_days <= settings.INTRADAY_MAX_DAYS + 1
    assert end.tzinfo is not None


def test_daily_window_uses_full_history(handler):
    start, end = handler._resolve_window("1d")
    assert start == datetime.strptime(settings.HISTORY_START, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    assert end == datetime.strptime(settings.HISTORY_END, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )


# --------------------------------------------------------------------------- #
# get_data end-to-end (mocked download) + caching round-trip
# --------------------------------------------------------------------------- #
def test_get_data_fetches_cleans_and_caches(handler):
    _patch_download(handler, _make_raw_1h(periods=24))
    df = handler.get_data("EURUSD", "1h", force_refresh=True)

    assert list(df.columns) == OHLCV_COLUMNS
    assert df.index.is_monotonic_increasing
    assert df.index.tz is not None
    assert len(df) == 24

    # cache file written
    cache_path = handler._cache_path("EURUSD", "1h")
    assert cache_path.exists()

    # second call loads from cache (download would now raise if called)
    def _boom(*a, **k):
        raise AssertionError("should have loaded from cache, not re-downloaded")

    handler._download = _boom  # type: ignore[method-assign]
    cached = handler.get_data("EURUSD", "1h")
    # Values and timestamps must match; index `freq` metadata is not preserved
    # through the parquet round-trip and we don't depend on it.
    pd.testing.assert_frame_equal(
        cached[OHLCV_COLUMNS],
        df[OHLCV_COLUMNS],
        check_dtype=False,
        check_freq=False,
    )


def test_get_data_4h_resamples_from_1h(handler):
    _patch_download(handler, _make_raw_1h(periods=24))
    df4 = handler.get_data("EURUSD", "4h", force_refresh=True)
    # 24 1h bars -> 6 4h bars
    assert len(df4) == 6
    assert list(df4.columns) == OHLCV_COLUMNS


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_unknown_pair_raises(handler):
    with pytest.raises(ValueError, match="Unknown pair"):
        handler.get_data("XAUUSD", "1h")


def test_unknown_timeframe_raises(handler):
    with pytest.raises(ValueError, match="Unknown timeframe"):
        handler.get_data("EURUSD", "30m")


def test_empty_download_returns_empty_frame(handler):
    _patch_download(handler, pd.DataFrame())
    out = handler.get_data("EURUSD", "1h", force_refresh=True)
    assert out.empty


# --------------------------------------------------------------------------- #
# Futures-volume merge (spot price + futures volume)
# --------------------------------------------------------------------------- #
def _ticker_aware_download(spot_frame, fut_frame):
    """Return a _download stand-in that serves spot vs futures by ticker."""
    def _dl(ticker, start, end, interval):
        return fut_frame if ticker.endswith("=F") else spot_frame
    return _dl


def test_futures_volume_replaces_spot_zero_volume(tmp_path):
    h = DataHandler(cache_dir=tmp_path, cache_enabled=False, use_futures_volume=True)
    spot = _make_raw_1h(periods=24)           # spot price (volume present but irrelevant)
    fut = _make_futures_vol(periods=24, base=100)
    h._download = _ticker_aware_download(spot, fut)  # type: ignore[method-assign]

    df = h.get_data("EURUSD", "1h", force_refresh=True)
    # Volume now equals the futures volume (index+1)*100, aligned by timestamp.
    expected = (np.arange(24) + 1) * 100
    np.testing.assert_array_equal(df["Volume"].to_numpy(), expected.astype(float))
    # Price columns are untouched (still the spot series).
    assert df["Close"].notna().all()


def test_futures_volume_alignment_by_timestamp(tmp_path):
    """Futures bars are matched to spot by timestamp; gaps -> 0, extras dropped."""
    h = DataHandler(cache_dir=tmp_path, cache_enabled=False, use_futures_volume=True)
    spot = _make_raw_1h(periods=10)
    # Futures missing the first 2 timestamps, has 3 extra later ones.
    fut = _make_futures_vol(periods=13, base=10).iloc[2:]
    h._download = _ticker_aware_download(spot, fut)  # type: ignore[method-assign]

    df = h.get_data("EURUSD", "1h", force_refresh=True)
    vols = df["Volume"].to_numpy()
    # First 2 spot rows had no matching futures bar -> 0.
    assert vols[0] == 0.0 and vols[1] == 0.0
    # Remaining rows matched their futures volume ((idx+1)*10).
    assert vols[2] == (2 + 1) * 10
    # Length follows SPOT (price) rows, not futures.
    assert len(df) == 10


def test_futures_volume_fallback_when_empty(tmp_path):
    """If futures fetch is empty, keep spot volume rather than crashing."""
    h = DataHandler(cache_dir=tmp_path, cache_enabled=False, use_futures_volume=True)
    spot = _make_raw_1h(periods=12)
    h._download = _ticker_aware_download(spot, pd.DataFrame())  # type: ignore[method-assign]

    df = h.get_data("EURUSD", "1h", force_refresh=True)
    # No crash; spot's own volume is retained.
    assert len(df) == 12
    assert "Volume" in df.columns


def test_futures_volume_off_keeps_spot_volume(tmp_path):
    h = DataHandler(cache_dir=tmp_path, cache_enabled=False, use_futures_volume=False)
    spot = _make_raw_1h(periods=12)
    requested = []

    def _dl(ticker, start, end, interval):
        requested.append(ticker)
        return spot

    h._download = _dl  # type: ignore[method-assign]
    df = h.get_data("EURUSD", "1h", force_refresh=True)
    # Only the spot ticker was requested (no futures fetch), and Volume is
    # exactly spot's own series.
    assert requested == [settings.PAIRS["EURUSD"]]
    np.testing.assert_array_equal(
        df["Volume"].to_numpy(), spot[("Volume", "EURUSD=X")].to_numpy()
    )


# --------------------------------------------------------------------------- #
# Derived timeframes (4h) are rebuilt from the cached 1h base
# --------------------------------------------------------------------------- #
def test_4h_is_derived_from_1h_and_never_cached(handler):
    _patch_download(handler, _make_raw_1h(periods=24))
    handler.get_data("EURUSD", "4h", force_refresh=True)
    assert handler._cache_path("EURUSD", "1h").exists()
    assert not handler._cache_path("EURUSD", "4h").exists()

    # A later 4h call rebuilds from the cached 1h base — no download.
    def _boom(*a, **k):
        raise AssertionError("4h should be rebuilt from the cached 1h base")

    handler._download = _boom  # type: ignore[method-assign]
    assert len(handler.get_data("EURUSD", "4h")) == 6


def test_4h_inherits_futures_volume(tmp_path):
    """The stale-4h bug: 4h must carry the (summed) futures volume of its 1h base."""
    h = DataHandler(cache_dir=tmp_path, cache_enabled=False, use_futures_volume=True)
    spot = _make_raw_1h(periods=8)
    fut = _make_futures_vol(periods=8, base=100)   # volumes 100..800
    h._download = _ticker_aware_download(spot, fut)  # type: ignore[method-assign]
    df4 = h.get_data("EURUSD", "4h", force_refresh=True)
    assert list(df4["Volume"]) == [100 + 200 + 300 + 400, 500 + 600 + 700 + 800]


def test_get_all_force_refresh_downloads_each_base_once(tmp_path):
    h = DataHandler(cache_dir=tmp_path, use_futures_volume=False)
    calls = []

    def _dl(ticker, start, end, interval):
        calls.append(ticker)
        return _make_raw_1h(periods=24)

    h._download = _dl  # type: ignore[method-assign]
    out = h.get_all(force_refresh=True)
    assert len(out) == len(settings.PAIRS) * len(settings.TIMEFRAMES)
    # 1h and 4h per pair, but only ONE download per pair (4h reuses 1h).
    assert sorted(calls) == sorted(settings.PAIRS.values())


# --------------------------------------------------------------------------- #
# Timestamps are normalised to UTC (Yahoo serves spot FX in London time)
# --------------------------------------------------------------------------- #
def _london_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-07-01 09:00", periods=3, freq="1h", tz="Europe/London")
    return pd.DataFrame({c: 1.0 for c in OHLCV_COLUMNS}, index=idx)


def test_clean_converts_index_to_utc(handler):
    out = handler._clean(_london_frame())
    assert str(out.index.tz) == "UTC"
    # BST is UTC+1: same instant, UTC wall-clock
    assert out.index[0] == pd.Timestamp("2024-07-01 08:00", tz="UTC")


def test_cache_load_converts_index_to_utc(handler, tmp_path):
    path = tmp_path / "london.parquet"
    _london_frame().to_parquet(path)
    out = handler._load_cache(path)
    assert str(out.index.tz) == "UTC"
    assert out.index[0] == pd.Timestamp("2024-07-01 08:00", tz="UTC")


# --------------------------------------------------------------------------- #
# Data-quality guard: warn when the volume series is (mostly) zero
# --------------------------------------------------------------------------- #
def test_zero_volume_series_warns(handler, caplog):
    raw = _make_raw_1h(periods=24)
    raw[("Volume", "EURUSD=X")] = 0.0
    _patch_download(handler, raw)
    with caplog.at_level(logging.WARNING, logger="src.data_handler"):
        handler.get_data("EURUSD", "1h", force_refresh=True)
    assert any("nonzero volume" in r.getMessage() for r in caplog.records)


def test_zero_volume_warns_on_cache_load_too(handler, caplog):
    raw = _make_raw_1h(periods=24)
    raw[("Volume", "EURUSD=X")] = 0.0
    _patch_download(handler, raw)
    handler.get_data("EURUSD", "1h", force_refresh=True)   # writes the cache
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="src.data_handler"):
        handler.get_data("EURUSD", "1h")                   # served from cache
    assert any("nonzero volume" in r.getMessage() for r in caplog.records)


def test_healthy_volume_does_not_warn(handler, caplog):
    _patch_download(handler, _make_raw_1h(periods=24))
    with caplog.at_level(logging.WARNING, logger="src.data_handler"):
        handler.get_data("EURUSD", "1h", force_refresh=True)
    assert not any("nonzero volume" in r.getMessage() for r in caplog.records)


# --------------------------------------------------------------------------- #
# Optional live network test (skipped by default)
# --------------------------------------------------------------------------- #
@pytest.mark.network
def test_real_yahoo_fetch_smoke(tmp_path):
    h = DataHandler(cache_dir=tmp_path)
    df = h.get_data("EURUSD", "1h", force_refresh=True)
    assert not df.empty
    assert set(OHLCV_COLUMNS).issubset(df.columns)


@pytest.mark.network
def test_real_futures_volume_is_nonzero(tmp_path):
    """End-to-end on live data: spot price + futures volume yields real volume."""
    h = DataHandler(cache_dir=tmp_path, use_futures_volume=True)
    df = h.get_data("EURUSD", "1h", force_refresh=True)
    assert not df.empty
    # The whole point of the merge: volume is no longer all zeros.
    assert df["Volume"].sum() > 0
    assert (df["Volume"] > 0).mean() > 0.5  # most rows have real volume
