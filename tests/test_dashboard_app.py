"""Streamlit AppTest coverage for dashboard/app.py.

Focus: the public-demo mode used for the hosted usability-study link must never show
broker credential inputs and must route Live mode to the paper broker, whatever
EXECUTION_HANDLER is set to.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from config import settings

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
APP = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")


def _run():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    return at


def _labels(widgets):
    return [w.label for w in widgets]


def test_private_mode_shows_credential_inputs(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_DEMO", False)
    at = _run()
    assert not at.exception
    assert "Login ID" in _labels(at.sidebar.text_input)


def test_public_demo_hides_credential_inputs(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_DEMO", True)
    at = _run()
    assert not at.exception
    labels = _labels(at.sidebar.text_input)
    for field in ("Login ID", "Password", "Server"):
        assert field not in labels
    assert any("Public Demo" in h.value for h in at.sidebar.header)


def test_public_demo_live_mode_is_paper_even_if_mt5_configured(monkeypatch):
    """A misconfigured hosted link must not try to reach a real broker."""
    monkeypatch.setattr(settings, "PUBLIC_DEMO", True)
    monkeypatch.setattr(settings, "EXECUTION_HANDLER", "mt5")
    at = _run()
    at.radio[0].set_value("Live (paper or MT5 demo)").run()
    assert not at.exception
    assert any("Paper mode" in s.value for s in at.success)
    assert any("simulated broker" in c.value for c in at.caption)


def test_backtest_runs_and_shows_metrics(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_DEMO", True)
    at = _run()
    at.sidebar.button[0].click().run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    for name in ("Win Rate", "Max Drawdown", "Profit Factor", "Sharpe", "Net P&L"):
        assert name in labels
