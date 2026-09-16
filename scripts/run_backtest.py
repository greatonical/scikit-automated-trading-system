"""End-to-end backtest on real data — the honest evaluation (README §8).

Pipeline: DataHandler -> Preprocessor -> MLModel (tuned) -> Backtester (mock),
then prints the §8 metrics and pass/fail vs targets, and saves the trained model
(with provenance metadata) to models/random_forest_<PAIR>_<TIMEFRAME>.pkl.

Every knob comes from config/settings.py and most can be overridden per run with
an env var, e.g. the Step A exits:
    DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 \\
        .venv/bin/python scripts/run_backtest.py EURUSD 1h

Usage:
    .venv/bin/python scripts/run_backtest.py [PAIR] [TIMEFRAME]
"""
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging  # noqa: E402
# Show warnings (e.g. the low-volume data guard) but not per-bar INFO chatter or
# the RiskManager's per-bar "trading halted" repeats.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("src.risk_manager").setLevel(logging.ERROR)

import pandas as pd  # noqa: E402

from config import settings  # noqa: E402
from src.backtester import Backtester  # noqa: E402
from src.data_handler import DataHandler  # noqa: E402
from src.execution.mock import MockExecutionHandler  # noqa: E402
from src.ml_model import MLModel  # noqa: E402
from src.preprocessor import Preprocessor  # noqa: E402
from src.risk_manager import RiskManager  # noqa: E402
from src.signal_generator import SignalGenerator  # noqa: E402


def config_summary() -> dict:
    """The strategy config this run used (printed + saved with the model)."""
    return {
        "label_method": settings.LABEL_METHOD,
        "stop_loss_pct": settings.DEFAULT_STOP_LOSS_PCT,
        "take_profit_pct": settings.DEFAULT_TAKE_PROFIT_PCT,
        "max_hold_bars": settings.TRIPLE_BARRIER_MAX_HOLD,
        "use_time_exit": settings.USE_TIME_EXIT,
        "label_dynamic_sl": settings.LABEL_DYNAMIC_SL,
        "allow_shorts": settings.ALLOW_SHORTS,
        "volume_threshold": settings.VOLUME_ZSCORE_THRESHOLD,
        "confidence_threshold": settings.ML_CONFIDENCE_THRESHOLD,
        "spread": settings.BACKTEST_SPREAD,
        "slippage": settings.BACKTEST_SLIPPAGE,
        "features": list(settings.FEATURE_COLUMNS),
    }


def main() -> None:
    pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"

    print(f"\n=== Backtest: {pair} {tf} ===")
    cfg = config_summary()
    print("config: " + ", ".join(f"{k}={v}" for k, v in cfg.items() if k != "features"))
    print(f"features: {cfg['features']}")

    df = DataHandler().get_data(pair, tf)
    pre = Preprocessor()
    transformed = pre.transform(df)
    train_df, test_df = pre.chronological_split(transformed)
    X_train, y_train = pre.features_and_labels(train_df)
    X_test, y_test = pre.features_and_labels(test_df)
    print(f"train={len(X_train)} test={len(X_test)} "
          f"({test_df.index.min().date()} -> {test_df.index.max().date()})")

    # Train on the training set only, tuned via TimeSeriesSplit.
    model = MLModel().tune(
        X_train, y_train,
        param_grid=settings.EVAL_PARAM_GRID,
        n_splits=settings.EVAL_CV_SPLITS,
    )
    test_probs = model.predict_proba(X_test)

    handler = MockExecutionHandler(
        spread=settings.BACKTEST_SPREAD, slippage=settings.BACKTEST_SLIPPAGE
    )
    bt = Backtester(
        signal_generator=SignalGenerator(),
        risk_manager=RiskManager(),
        execution_handler=handler,
        symbol=pair,
    )
    res = bt.run(test_df, test_probs)

    print("\n--- Results (with spread+slippage) ---")
    for k, v in res.as_dict().items():
        print(f"  {k:16}: {v}")
    print(f"  win-rate CI     : [{res.win_rate_ci_low:.1%}, {res.win_rate_ci_high:.1%}] "
          f"(Wilson, z={settings.WIN_RATE_CI_Z}, n={res.n_trades})")

    if res.trades:
        tr = pd.DataFrame(res.trades)
        print("\n--- Trade breakdown ---")
        for side, g in tr.groupby("side"):
            print(f"  {side:4}: {len(g)} trades, win {(g['pnl'] > 0).mean():.1%}, "
                  f"net {g['pnl'].sum():+.2f}")
        print(f"  exits: {tr['exit_reason'].value_counts().to_dict()}")
        print(f"  bars held: median {tr['bars_held'].median():.0f}, "
              f"max {tr['bars_held'].max():.0f}")

    print("\n--- vs README §8 targets ---")
    targets = res.meets_targets()
    labels = {
        "win_rate": f"Win Rate > {settings.TARGET_WIN_RATE:.0%}",
        "max_drawdown": f"Max Drawdown < {settings.TARGET_MAX_DRAWDOWN:.0%}",
        "profit_factor": f"Profit Factor > {settings.TARGET_PROFIT_FACTOR}",
        "sharpe": f"Sharpe > {settings.TARGET_SHARPE} (per-trade, unannualised)",
    }
    for key, ok in targets.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {labels[key]}")

    print(f"\n  Trades taken: {res.n_trades} "
          f"(of {len(test_df)} candles) | net P&L: {res.net_pnl:+.2f}")

    path = settings.MODELS_DIR / settings.MODEL_FILENAME_TEMPLATE.format(
        pair=pair, timeframe=tf
    )
    model.save(path, metadata={
        "pair": pair,
        "timeframe": tf,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_window": [str(train_df.index.min()), str(train_df.index.max())],
        "test_window": [str(test_df.index.min()), str(test_df.index.max())],
        "n_train": len(train_df),
        "n_test": len(test_df),
        "cv_splits": settings.EVAL_CV_SPLITS,
        **cfg,
    })
    print(f"  Model saved -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
