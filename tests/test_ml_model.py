"""Tests for MLModel (Module 3).

Load-bearing checks (README §1/§5/§6):
  * The classifier is a RandomForest — never a deep-learning model.
  * Hyperparameter tuning uses TimeSeriesSplit (NOT KFold).
  * Tuning only ever sees the data you pass it (the training set).
  * predict_proba returns P(bullish) in [0, 1].
  * save/load round-trips to identical predictions.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit

from config import settings
from src.ml_model import MLModel


# --------------------------------------------------------------------------- #
# Helpers — build a learnable, time-ordered dataset
# --------------------------------------------------------------------------- #
def _xy(n: int = 300, seed: int = 0):
    """Feature matrix where the label is (mostly) a function of the features,
    so the model can actually learn something."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="1h", tz="UTC")
    close = 1.10 + np.cumsum(rng.normal(0, 0.001, n))
    z_close = rng.normal(0, 1, n)
    z_vol = rng.normal(0, 1, n)
    X = pd.DataFrame(
        {
            "Open": close, "High": close + 0.001, "Low": close - 0.001,
            "Close": close, "Volume": rng.integers(1000, 5000, n).astype(float),
            "ZScore_Close": z_close, "ZScore_Volume": z_vol,
            "RSI": rng.uniform(20, 80, n),       # indicator features, kept only if
            "MACD": rng.normal(0, 0.001, n),     # the active config uses them
            "MACD_Signal": rng.normal(0, 0.001, n),
            "MACD_Hist": rng.normal(0, 0.001, n),
            "ATR": rng.uniform(0.0005, 0.003, n),
            "TrendDist": rng.normal(0, 0.01, n),
            "TrendUp": rng.integers(0, 2, n).astype(float),
        },
        index=idx,
    )
    # Keep only the columns the active config actually uses, so these model tests
    # track FEATURE_COLUMNS as indicators are toggled on/off.
    from config import settings
    X = X[[c for c in settings.FEATURE_COLUMNS if c in X.columns]]
    # Label depends on z_close (+ noise) so there's a real signal to fit.
    logit = 2.0 * z_close + rng.normal(0, 0.5, n)
    y = pd.Series((logit > 0).astype(int), index=idx)
    return X, y


@pytest.fixture
def small_grid():
    return {"n_estimators": [50], "max_depth": [3, 5], "min_samples_leaf": [1, 2]}


# --------------------------------------------------------------------------- #
# It's a Random Forest (and nothing else)
# --------------------------------------------------------------------------- #
def test_train_produces_random_forest():
    X, y = _xy()
    m = MLModel(params={"n_estimators": 30, "random_state": 42}).train(X, y)
    assert isinstance(m.model, RandomForestClassifier)


def test_no_deep_learning_anywhere():
    """README §1: no tensorflow/keras/torch — in any import or requirements file."""
    import re
    import sys
    from pathlib import Path

    banned = ("tensorflow", "keras", "torch")
    root = Path(__file__).resolve().parent.parent

    # 1) No import statement anywhere in the project's Python code.
    import_re = re.compile(r"^\s*(?:import|from)\s+(?:%s)\b" % "|".join(banned), re.M)
    py_files = [p for d in ("src", "config", "dashboard", "scripts", "tests")
                for p in (root / d).rglob("*.py")]
    assert py_files
    for p in py_files:
        assert not import_re.search(p.read_text()), f"deep-learning import in {p}"

    # 2) No banned package in any requirements*.txt (comments ignored).
    req_files = list(root.glob("requirements*.txt"))
    assert req_files
    for req in req_files:
        for line in req.read_text().splitlines():
            spec = line.split("#", 1)[0].strip().lower()
            if spec:
                name = re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0]
                assert name not in banned, f"{name} listed in {req.name}"

    # 3) Importing the engine doesn't drag one in transitively.
    import dashboard.service  # noqa: F401
    import src.backtester  # noqa: F401
    import src.ml_model  # noqa: F401
    for b in banned:
        assert b not in sys.modules


# --------------------------------------------------------------------------- #
# Tuning uses TimeSeriesSplit, not KFold
# --------------------------------------------------------------------------- #
def test_tune_uses_timeseriessplit(small_grid):
    X, y = _xy()
    captured = {}

    real_init = TimeSeriesSplit.__init__

    def spy_init(self, *a, **k):
        captured["used"] = True
        return real_init(self, *a, **k)

    with patch.object(TimeSeriesSplit, "__init__", spy_init):
        with patch("src.ml_model.GridSearchCV") as MockGS:
            # Make the mock behave enough to finish .tune()
            instance = MockGS.return_value
            instance.best_estimator_ = RandomForestClassifier(
                n_estimators=10, random_state=42
            ).fit(X[settings.FEATURE_COLUMNS], y)
            instance.best_params_ = {"max_depth": 5}
            instance.best_score_ = 0.6
            instance.cv_results_ = {}
            MLModel().tune(X, y, param_grid=small_grid)

            # The cv passed to GridSearchCV must be a TimeSeriesSplit instance.
            _, kwargs = MockGS.call_args
            assert isinstance(kwargs["cv"], TimeSeriesSplit)
    assert captured.get("used") is True


def test_tune_real_run_sets_best_params(small_grid):
    X, y = _xy(250)
    m = MLModel().tune(X, y, param_grid=small_grid, n_splits=3)
    assert m.best_params_ is not None
    assert m.model is not None
    # best_params keys come from our grid
    assert set(m.best_params_).issubset(set(small_grid))


def test_tune_only_sees_training_data(small_grid):
    """Tune must fit on exactly the rows handed to it — never the test set."""
    X, y = _xy(200)
    X_train, X_test = X.iloc[:160], X.iloc[160:]
    y_train, y_test = y.iloc[:160], y.iloc[160:]

    seen = {}
    real_fit = RandomForestClassifier.fit

    def spy_fit(self, Xf, yf, *a, **k):
        seen.setdefault("max_index", []).append(
            Xf.index.max() if hasattr(Xf, "index") else None
        )
        return real_fit(self, Xf, yf, *a, **k)

    with patch.object(RandomForestClassifier, "fit", spy_fit):
        MLModel().tune(X_train, y_train, param_grid=small_grid, n_splits=3)

    # Every fit during tuning stayed within the training window.
    test_start = X_test.index.min()
    assert all(mi < test_start for mi in seen["max_index"] if mi is not None)


# --------------------------------------------------------------------------- #
# predict / predict_proba
# --------------------------------------------------------------------------- #
def test_predict_proba_is_bullish_prob_in_range():
    X, y = _xy()
    m = MLModel(params={"n_estimators": 50, "random_state": 42}).train(X, y)
    proba = m.predict_proba(X)
    assert proba.shape == (len(X),)
    assert (proba >= 0).all() and (proba <= 1).all()


def test_predict_proba_matches_class1_column():
    X, y = _xy()
    m = MLModel(params={"n_estimators": 40, "random_state": 42}).train(X, y)
    full = m.model.predict_proba(X[settings.FEATURE_COLUMNS])
    class1_col = list(m.model.classes_).index(1)
    np.testing.assert_allclose(m.predict_proba(X), full[:, class1_col])


def test_predict_before_fit_raises():
    with pytest.raises(RuntimeError, match="not fitted"):
        MLModel().predict(_xy()[0])


def test_missing_feature_column_raises():
    X, y = _xy()
    m = MLModel(params={"n_estimators": 10, "random_state": 42}).train(X, y)
    with pytest.raises(KeyError, match="Missing feature"):
        m.predict(X.drop(columns=["ZScore_Close"]))


# --------------------------------------------------------------------------- #
# Feature importances (interpretability)
# --------------------------------------------------------------------------- #
def test_feature_importances_sum_to_one():
    X, y = _xy()
    m = MLModel(params={"n_estimators": 50, "random_state": 42}).train(X, y)
    imp = m.feature_importances()
    assert list(imp.index) == sorted(imp.index, key=lambda c: -imp[c])
    assert imp.sum() == pytest.approx(1.0, rel=1e-6)
    # ZScore_Close drove the label, so it should rank highly.
    assert imp.index[0] == "ZScore_Close"


# --------------------------------------------------------------------------- #
# Persistence round-trip
# --------------------------------------------------------------------------- #
def test_save_load_roundtrip_identical_predictions(tmp_path):
    X, y = _xy()
    m = MLModel(params={"n_estimators": 60, "random_state": 42}).train(X, y)
    path = m.save(tmp_path / "rf.pkl")
    assert path.exists()

    loaded = MLModel.load(path)
    np.testing.assert_array_equal(m.predict(X), loaded.predict(X))
    np.testing.assert_allclose(m.predict_proba(X), loaded.predict_proba(X))
    assert loaded.feature_columns == m.feature_columns


def test_save_before_fit_raises(tmp_path):
    with pytest.raises(RuntimeError, match="not fitted"):
        MLModel().save(tmp_path / "x.pkl")


def test_save_load_roundtrip_keeps_provenance_metadata(tmp_path):
    X, y = _xy()
    m = MLModel(params={"n_estimators": 20, "random_state": 42}).train(X, y)
    meta = {"pair": "EURUSD", "timeframe": "1h", "stop_loss_pct": 0.012}
    path = m.save(tmp_path / "rf.pkl", metadata=meta)
    assert MLModel.load(path).metadata == meta


def test_load_legacy_model_without_metadata(tmp_path):
    import joblib
    X, y = _xy()
    m = MLModel(params={"n_estimators": 20, "random_state": 42}).train(X, y)
    # The pre-provenance payload format (no "metadata" key).
    joblib.dump({"model": m.model, "feature_columns": m.feature_columns,
                 "params": m.params, "best_params_": None}, tmp_path / "old.pkl")
    loaded = MLModel.load(tmp_path / "old.pkl")
    assert loaded.metadata == {}
    np.testing.assert_array_equal(loaded.predict(X), m.predict(X))
