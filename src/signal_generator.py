"""SignalGenerator — Module 4 (README §10 step 4).

The hybrid decision layer — the heart of the system. A trade fires ONLY when
BOTH gates agree (README §2):

  1. Rule gate:  Volume Z-Score  >  VOLUME_ZSCORE_THRESHOLD (+1.5)
  2. ML gate:    P(bullish)      >  ML_CONFIDENCE_THRESHOLD

If either gate fails -> HOLD (no trade). When both pass, the ML probability also
picks the direction: high P(bullish) -> BUY, low -> SELL. The SELL side is this
implementation's symmetric extension (README §2 states the gate on the bullish
class only) and can be switched off with ALLOW_SHORTS=false (long-only).

Every decision is logged (rule result + probability + final action) for
transparency and viva defence (README §12).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


class Action(str, Enum):
    """Final decision for one candle."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    """A single, fully-explained decision (transparency record)."""

    action: Action
    probability: float          # P(bullish) from the model
    volume_zscore: float        # Volume Z-Score for this candle
    rule_pass: bool             # did the +1.5 volume gate pass?
    ml_pass: bool               # did the ML confidence gate pass?
    timestamp: pd.Timestamp | None = None

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "action": self.action.value,
            "probability": round(self.probability, 4),
            "volume_zscore": round(self.volume_zscore, 4),
            "rule_pass": self.rule_pass,
            "ml_pass": self.ml_pass,
        }


class SignalGenerator:
    """Turn (volume Z-score, ML probability) into BUY / SELL / HOLD."""

    def __init__(
        self,
        volume_threshold: float | None = None,
        confidence_threshold: float | None = None,
        allow_shorts: bool | None = None,
    ) -> None:
        self.volume_threshold = (
            volume_threshold
            if volume_threshold is not None
            else settings.VOLUME_ZSCORE_THRESHOLD
        )
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.ML_CONFIDENCE_THRESHOLD
        )
        self.allow_shorts = (
            allow_shorts if allow_shorts is not None else settings.ALLOW_SHORTS
        )

    # ------------------------------------------------------------------ #
    # Single decision
    # ------------------------------------------------------------------ #
    def decide(
        self,
        probability: float,
        volume_zscore: float,
        timestamp: pd.Timestamp | None = None,
    ) -> Signal:
        """Apply the hybrid AND-logic to one candle.

        * rule_pass = volume Z-Score strictly exceeds the +1.5 threshold.
        * ml_pass   = P(bullish) strictly exceeds the confidence threshold
                      (for a SELL — only when shorts are allowed — we require
                      the bearish side to be confident, i.e. P(bullish) < 1 - threshold).
        Both must agree for a trade; direction comes from the probability.
        """
        rule_pass = volume_zscore > self.volume_threshold

        bullish_pass = probability > self.confidence_threshold
        bearish_pass = self.allow_shorts and probability < (
            1.0 - self.confidence_threshold
        )
        ml_pass = bullish_pass or bearish_pass

        if rule_pass and bullish_pass:
            action = Action.BUY
        elif rule_pass and bearish_pass:
            action = Action.SELL
        else:
            action = Action.HOLD

        signal = Signal(
            action=action,
            probability=float(probability),
            volume_zscore=float(volume_zscore),
            rule_pass=rule_pass,
            ml_pass=ml_pass,
            timestamp=timestamp,
        )
        logger.info(
            "Signal %s | P(bull)=%.3f vol_z=%.3f rule=%s ml=%s -> %s",
            timestamp,
            probability,
            volume_zscore,
            rule_pass,
            ml_pass,
            action.value,
        )
        return signal

    # ------------------------------------------------------------------ #
    # Batch over a dataset
    # ------------------------------------------------------------------ #
    def generate(
        self, probabilities, volume_zscores, index=None
    ) -> list[Signal]:
        """Produce a Signal for each row of probabilities / volume Z-scores."""
        probs = list(probabilities)
        vols = list(volume_zscores)
        if len(probs) != len(vols):
            raise ValueError("probabilities and volume_zscores length mismatch")
        idx = list(index) if index is not None else [None] * len(probs)

        return [
            self.decide(p, v, ts) for p, v, ts in zip(probs, vols, idx)
        ]

    def to_frame(self, signals: list[Signal]) -> pd.DataFrame:
        """Render a list of Signals as a DataFrame (for logging/inspection)."""
        return pd.DataFrame([s.as_dict() for s in signals])
