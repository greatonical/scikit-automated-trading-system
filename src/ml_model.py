"""MLModel — Module 3 (README §10 step 3).

Wraps a scikit-learn RandomForestClassifier with the project's guardrails baked
in:

* **Random Forest only** (README §1) — no deep learning, ever.
* **Hyperparameter tuning uses `TimeSeriesSplit`, never `KFold`** (README §5/§6),
  and runs on the TRAINING set only. The hold-out test set is never seen during
  tuning, so reported metrics reflect genuine out-of-sample skill.
* **Persistence via `joblib`** to `models/` (README §12).
* Exposes `predict_proba` so the SignalGenerator can apply the ML confidence
  gate of the hybrid logic.

Why Random Forest (README §1): runs on a normal CPU, resists overfitting via
ensemble averaging, and is interpretable through feature importances.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

from config import settings

logger = logging.getLogger(__name__)


class MLModel:
    """Random Forest classifier for bullish-continuation prediction."""

    def __init__(
        self,
        params: dict | None = None,
        feature_columns: list[str] | None = None,
    ) -> None:
        self.feature_columns = (
            feature_columns
            if feature_columns is not None
            else list(settings.FEATURE_COLUMNS)
        )
        # Start from the configured defaults; CV tuning may replace these.
        self.params = dict(params) if params is not None else dict(
            settings.RF_DEFAULT_PARAMS
        )
        self.model: RandomForestClassifier | None = None
        self.best_params_: dict | None = None
        self.cv_results_: dict | None = None
        # Provenance saved with the model (pair, data window, label/exit config…)
        # so a .pkl on disk says exactly what produced it.
        self.metadata: dict = {}

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #
    def train(self, X: pd.DataFrame, y: pd.Series) -> "MLModel":
        """Fit a Random Forest with the current ``params`` (no tuning)."""
        X = self._select_features(X)
        self.model = RandomForestClassifier(**self.params)
        self.model.fit(X, y)
        logger.info("Trained RandomForest on %d rows with params=%s", len(X), self.params)
        return self

    def tune(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        param_grid: dict | None = None,
        n_splits: int | None = None,
        scoring: str = "accuracy",
    ) -> "MLModel":
        """Tune hyperparameters via TimeSeriesSplit CV on the TRAINING set only.

        Uses `GridSearchCV` with a `TimeSeriesSplit` (expanding-window) splitter
        — NOT the default `KFold`, which would shuffle time order and leak the
        future. After tuning, the best estimator is kept and `best_params_` /
        `cv_results_` are recorded for the report.
        """
        X = self._select_features(X)
        grid = param_grid if param_grid is not None else settings.RF_PARAM_GRID
        splits = n_splits if n_splits is not None else settings.CV_N_SPLITS

        # Fixed estimator settings that are NOT tuned (seed, parallelism).
        base = RandomForestClassifier(
            random_state=settings.RF_RANDOM_STATE,
            n_jobs=settings.RF_N_JOBS,
        )
        cv = TimeSeriesSplit(n_splits=splits)

        search = GridSearchCV(
            estimator=base,
            param_grid=grid,
            cv=cv,                 # <-- TimeSeriesSplit, never KFold
            scoring=scoring,
            n_jobs=settings.RF_N_JOBS,
        )
        search.fit(X, y)

        self.model = search.best_estimator_
        self.best_params_ = search.best_params_
        self.cv_results_ = search.cv_results_
        # Merge tuned params over fixed ones so a later .train() reproduces them.
        self.params = {**self.params, **search.best_params_}
        logger.info(
            "Tuned via TimeSeriesSplit(%d): best=%s score=%.4f",
            splits,
            search.best_params_,
            search.best_score_,
        )
        return self

    # ------------------------------------------------------------------ #
    # Prediction
    # ------------------------------------------------------------------ #
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict class labels (0 = bearish/neutral, 1 = bullish)."""
        self._require_fitted()
        return self.model.predict(self._select_features(X))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Probability of the bullish class (1) for each row.

        Returns a 1-D array of P(class == 1). The SignalGenerator compares this
        against `ML_CONFIDENCE_THRESHOLD` for the hybrid logic's ML gate.
        """
        self._require_fitted()
        proba = self.model.predict_proba(self._select_features(X))
        # Locate the column for class label 1 (don't assume ordering).
        classes = list(self.model.classes_)
        if 1 in classes:
            return proba[:, classes.index(1)]
        # Degenerate case: model only ever saw one class.
        return np.zeros(len(X)) if 1 not in classes else proba[:, 0]

    # ------------------------------------------------------------------ #
    # Interpretability (README §1 — transparency goal)
    # ------------------------------------------------------------------ #
    def feature_importances(self) -> pd.Series:
        """Return feature importances as a sorted Series (most important first)."""
        self._require_fitted()
        return pd.Series(
            self.model.feature_importances_, index=self.feature_columns
        ).sort_values(ascending=False)

    # ------------------------------------------------------------------ #
    # Persistence (joblib — README §12)
    # ------------------------------------------------------------------ #
    def save(self, path: str | Path | None = None, metadata: dict | None = None) -> Path:
        """Persist the fitted model (+ metadata) to disk via joblib.

        ``metadata`` (default: ``self.metadata``) records provenance — pair,
        timeframe, data window, label/exit config — alongside the model.
        """
        self._require_fitted()
        path = Path(path) if path is not None else settings.MODELS_DIR / settings.MODEL_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        if metadata is not None:
            self.metadata = dict(metadata)
        payload = {
            "model": self.model,
            "feature_columns": self.feature_columns,
            "params": self.params,
            "best_params_": self.best_params_,
            "metadata": self.metadata,
        }
        joblib.dump(payload, path)
        logger.info("Saved model -> %s", path)
        return path

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MLModel":
        """Load a persisted model back into a ready-to-predict MLModel."""
        path = Path(path) if path is not None else settings.MODELS_DIR / settings.MODEL_FILENAME
        payload = joblib.load(path)
        obj = cls(
            params=payload.get("params"),
            feature_columns=payload.get("feature_columns"),
        )
        obj.model = payload["model"]
        obj.best_params_ = payload.get("best_params_")
        obj.metadata = payload.get("metadata") or {}
        logger.info("Loaded model <- %s", path)
        return obj

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _select_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Keep only the configured feature columns, in order."""
        missing = [c for c in self.feature_columns if c not in X.columns]
        if missing:
            raise KeyError(f"Missing feature columns: {missing}")
        return X[self.feature_columns]

    def _require_fitted(self) -> None:
        if self.model is None:
            raise RuntimeError("Model is not fitted. Call train() or tune() first.")
