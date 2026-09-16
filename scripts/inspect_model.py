"""Human-readable view of saved model .pkl files (run, don't open the binary).

Usage:
    .venv/bin/python scripts/inspect_model.py                  # every models/*.pkl
    .venv/bin/python scripts/inspect_model.py models/random_forest_EURUSD_1h.pkl
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from src.ml_model import MLModel  # noqa: E402


def show(path: Path) -> None:
    m = MLModel.load(path)
    rf = m.model

    print("=" * 60)
    print("MODEL FILE:", path)
    print("=" * 60)
    print("Type            :", type(rf).__name__)
    print("Trees           :", rf.n_estimators)
    print("Max depth       :", rf.max_depth)
    print("Min samples/leaf:", rf.min_samples_leaf)
    print("Classes         :", [int(c) for c in rf.classes_])
    print("Features        :", m.feature_columns)
    print("Tuned params    :", m.best_params_)
    if m.metadata:
        print("Provenance:")
        for k, v in m.metadata.items():
            if k != "features":
                print(f"  {k:22}: {v}")
    else:
        print("Provenance      : none saved — this model predates provenance "
              "metadata; treat it as stale and re-run scripts/run_backtest.py")
    print()
    print("Feature importances (most → least):")
    print(m.feature_importances().round(4).to_string())
    print()


def main() -> None:
    paths = [Path(a) for a in sys.argv[1:]] or sorted(settings.MODELS_DIR.glob("*.pkl"))
    if not paths:
        print("No models in models/. Run scripts/run_backtest.py first.")
        return
    for p in paths:
        show(p)


if __name__ == "__main__":
    main()
