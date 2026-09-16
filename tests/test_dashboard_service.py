"""Tests for the dashboard service layer (Module 9).

These test the dashboard's LOGIC without launching Streamlit. The full
train+backtest path is exercised on synthetic data so it's fast and offline.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import settings
from dashboard import service
from src.preprocessor import Preprocessor


def _synthetic_ohlcv(n: int = 400, seed: int = 1) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 1.10 + np.cumsum(rng.normal(0, 0.001, n))
    return pd.DataFrame(
        {
            "Open": close, "High": close + 0.002, "Low": close - 0.002,
            "Close": close, "Volume": rng.integers(1000, 5000, n).astype(float),
        },
        index=idx,
    )


# --------------------------------------------------------------------------- #
# Credentials status (never leaks the password)
# --------------------------------------------------------------------------- #
def test_credentials_status_all_set():
    s = service.credentials_status("123", "pw", "Broker-Demo")
    assert s == {"login_set": True, "password_set": True,
                 "server_set": True, "ready": True}


def test_credentials_status_incomplete():
    s = service.credentials_status("123", "", "Broker-Demo")
    assert s["ready"] is False
    assert s["password_set"] is False


def test_credentials_status_returns_no_secret_values():
    s = service.credentials_status("user", "supersecret", "srv")
    # Only booleans — the actual password must never appear.
    assert "supersecret" not in str(s)
    assert all(isinstance(v, bool) for v in s.values())


# --------------------------------------------------------------------------- #
# Prepare / train / backtest path
# --------------------------------------------------------------------------- #
def test_prepare_split_returns_chronological():
    df = _synthetic_ohlcv()
    train_df, test_df, pre = service.prepare_split(df)
    assert isinstance(pre, Preprocessor)
    assert train_df.index.max() < test_df.index.min()


def test_train_and_backtest_runs_end_to_end():
    df = _synthetic_ohlcv()
    train_df, test_df, pre = service.prepare_split(df)
    model = service.train_model(pre, train_df, quick=True)
    result = service.run_backtest(
        pre, model, test_df,
        pair="EURUSD",
        volume_threshold=1.5,
        confidence_threshold=0.55,
        risk_fraction=0.01,
    )
    # Result has the metric fields the UI displays.
    for attr in ["win_rate", "max_drawdown", "profit_factor", "sharpe", "n_trades",
                 "win_rate_ci_low", "win_rate_ci_high"]:
        assert hasattr(result, attr)


def test_quick_training_uses_the_shared_evaluation_grid(monkeypatch):
    """The dashboard must tune like scripts/run_backtest.py so numbers agree."""
    seen = {}

    def fake_tune(self, X, y, param_grid=None, n_splits=None, scoring="accuracy"):
        seen["grid"], seen["splits"] = param_grid, n_splits
        return self

    monkeypatch.setattr(service.MLModel, "tune", fake_tune)
    df = _synthetic_ohlcv()
    train_df, _, pre = service.prepare_split(df)
    service.train_model(pre, train_df, quick=True)
    assert seen == {"grid": settings.EVAL_PARAM_GRID, "splits": settings.EVAL_CV_SPLITS}


# --------------------------------------------------------------------------- #
# Chart frames
# --------------------------------------------------------------------------- #
def test_equity_curve_frame_shape():
    df = _synthetic_ohlcv()
    train_df, test_df, pre = service.prepare_split(df)
    model = service.train_model(pre, train_df, quick=True)
    result = service.run_backtest(
        pre, model, test_df, pair="EURUSD",
        volume_threshold=1.5, confidence_threshold=0.55, risk_fraction=0.01,
    )
    ec = service.equity_curve_frame(result)
    assert "equity" in ec.columns
    assert len(ec) == len(result.equity_curve)


# --------------------------------------------------------------------------- #
# Live-mode helpers — routed by EXECUTION_HANDLER through the factory
# --------------------------------------------------------------------------- #
def test_live_service_status_unreachable_is_graceful():
    # Nothing listening on port 1 -> reachable False, friendly detail, no raise.
    status = service.live_service_status(host="127.0.0.1", port=1, handler="remote_mt5")
    assert status["handler"] == "remote_mt5"
    assert status["reachable"] is False
    assert "unreachable" in status["detail"]


def test_send_live_signal_unreachable_returns_error():
    res = service.send_live_signal(
        symbol="EURUSD", side="BUY", volume_lots=0.1, sl=1.09, tp=1.12,
        host="127.0.0.1", port=1, handler="remote_mt5",
    )
    assert res["status"] == "error"
    assert "unreachable" in res["error"].lower()


def test_live_status_paper_mode_is_reachable():
    status = service.live_service_status(handler="mock")
    assert status["handler"] == "mock"
    assert status["reachable"] is True
    assert "Paper" in status["detail"]


def test_live_route_follows_execution_handler_setting(monkeypatch):
    """Swapping paper <-> MT5 routing is ONE config change (EXECUTION_HANDLER)."""
    monkeypatch.setattr(settings, "EXECUTION_HANDLER", "mock")
    assert service.live_service_status()["handler"] == "mock"
    monkeypatch.setattr(settings, "EXECUTION_HANDLER", "remote_mt5")
    status = service.live_service_status(host="127.0.0.1", port=1)
    assert status["handler"] == "remote_mt5"
    assert status["reachable"] is False


def test_unknown_handler_status_is_graceful():
    status = service.live_service_status(handler="bogus")
    assert status["reachable"] is False
    assert "Unknown execution handler" in status["detail"]


def test_send_live_signal_paper_fills_at_reference_price_in_units():
    res = service.send_live_signal(
        symbol="EURUSD", side="BUY", volume_lots=0.1, sl=1.09, tp=1.12,
        price=1.1, handler="mock",
    )
    assert res["status"] == "filled"
    assert res["price"] == pytest.approx(1.1)     # the reference price
    assert res["volume"] == pytest.approx(0.1 * settings.FX_STANDARD_LOT_UNITS)
    assert res["latency_ms"] >= 0


def test_send_live_signal_paper_without_price_returns_error():
    res = service.send_live_signal(
        symbol="EURUSD", side="BUY", volume_lots=0.1, sl=1.09, tp=1.12,
        handler="mock",
    )
    assert res["status"] == "error"
    assert "price" in res["error"]


def test_trades_frame_empty_safe():
    # Build a result with no trades (impossible thresholds).
    df = _synthetic_ohlcv()
    train_df, test_df, pre = service.prepare_split(df)
    model = service.train_model(pre, train_df, quick=True)
    result = service.run_backtest(
        pre, model, test_df, pair="EURUSD",
        volume_threshold=99.0,  # never fires
        confidence_threshold=0.55, risk_fraction=0.01,
    )
    tf = service.trades_frame(result)
    assert isinstance(tf, pd.DataFrame)
    assert result.n_trades == 0
    assert tf.empty
