"""Tests for SignalGenerator (Module 4).

The load-bearing test is the hybrid truth table (README §2):
trade ONLY when BOTH the +1.5 volume rule AND the ML confidence gate agree;
either failing -> HOLD. Direction comes from the probability.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.signal_generator import Action, SignalGenerator


@pytest.fixture
def gen():
    # explicit thresholds so tests don't depend on config defaults
    return SignalGenerator(volume_threshold=1.5, confidence_threshold=0.55,
                           allow_shorts=True)


# --------------------------------------------------------------------------- #
# Hybrid truth table — the core of the system
# --------------------------------------------------------------------------- #
def test_both_pass_bullish_gives_buy(gen):
    # volume high (2.0 > 1.5) AND bullish confident (0.7 > 0.55)
    s = gen.decide(probability=0.70, volume_zscore=2.0)
    assert s.action is Action.BUY
    assert s.rule_pass and s.ml_pass


def test_both_pass_bearish_gives_sell(gen):
    # volume high AND bearish confident (0.20 < 1-0.55=0.45)
    s = gen.decide(probability=0.20, volume_zscore=2.0)
    assert s.action is Action.SELL
    assert s.rule_pass and s.ml_pass


def test_rule_fails_gives_hold(gen):
    # ML confident but volume too low (1.0 < 1.5) -> HOLD
    s = gen.decide(probability=0.90, volume_zscore=1.0)
    assert s.action is Action.HOLD
    assert s.rule_pass is False


def test_ml_fails_gives_hold(gen):
    # volume high but ML not confident either way (0.50 is between 0.45 and 0.55)
    s = gen.decide(probability=0.50, volume_zscore=3.0)
    assert s.action is Action.HOLD
    assert s.ml_pass is False


def test_both_fail_gives_hold(gen):
    s = gen.decide(probability=0.50, volume_zscore=0.0)
    assert s.action is Action.HOLD
    assert not s.rule_pass and not s.ml_pass


# --------------------------------------------------------------------------- #
# Boundary behaviour (strict ">" — exactly at threshold does NOT pass)
# --------------------------------------------------------------------------- #
def test_volume_exactly_at_threshold_holds(gen):
    s = gen.decide(probability=0.90, volume_zscore=1.5)  # not strictly > 1.5
    assert s.rule_pass is False
    assert s.action is Action.HOLD


def test_probability_exactly_at_threshold_holds(gen):
    s = gen.decide(probability=0.55, volume_zscore=2.0)  # not strictly > 0.55
    assert s.ml_pass is False
    assert s.action is Action.HOLD


# --------------------------------------------------------------------------- #
# Batch generation
# --------------------------------------------------------------------------- #
def test_generate_batch_matches_individual(gen):
    probs = [0.70, 0.20, 0.90, 0.50]
    vols = [2.0, 2.0, 1.0, 3.0]
    idx = pd.date_range("2024-01-01", periods=4, freq="1h", tz="UTC")
    signals = gen.generate(probs, vols, index=idx)

    actions = [s.action for s in signals]
    assert actions == [Action.BUY, Action.SELL, Action.HOLD, Action.HOLD]
    # timestamps carried through
    assert signals[0].timestamp == idx[0]


def test_generate_length_mismatch_raises(gen):
    with pytest.raises(ValueError, match="length mismatch"):
        gen.generate([0.5, 0.6], [1.0])


def test_to_frame_has_transparency_columns(gen):
    signals = gen.generate([0.7, 0.2], [2.0, 2.0])
    df = gen.to_frame(signals)
    for col in ["action", "probability", "volume_zscore", "rule_pass", "ml_pass"]:
        assert col in df.columns
    assert list(df["action"]) == ["BUY", "SELL"]


# --------------------------------------------------------------------------- #
# Config-driven thresholds
# --------------------------------------------------------------------------- #
def test_custom_thresholds_respected():
    g = SignalGenerator(volume_threshold=3.0, confidence_threshold=0.8)
    # 2.0 volume now fails the stricter 3.0 gate
    assert g.decide(0.95, 2.0).action is Action.HOLD
    # but a 4.0 volume + 0.85 prob passes
    assert g.decide(0.85, 4.0).action is Action.BUY


# --------------------------------------------------------------------------- #
# Long-only mode (ALLOW_SHORTS=false)
# --------------------------------------------------------------------------- #
def test_long_only_turns_sells_into_holds():
    g = SignalGenerator(volume_threshold=1.5, confidence_threshold=0.55,
                        allow_shorts=False)
    s = g.decide(probability=0.20, volume_zscore=2.0)  # would be a SELL
    assert s.action is Action.HOLD
    assert s.rule_pass is True
    assert s.ml_pass is False
    # the bullish side is unaffected
    assert g.decide(0.70, 2.0).action is Action.BUY


def test_allow_shorts_default_comes_from_config():
    from config import settings
    assert SignalGenerator().allow_shorts is settings.ALLOW_SHORTS
