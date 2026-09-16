"""Step C — threshold tuning (README §8 improvement phase).

Tunes the strategy's knobs (volume gate, ML confidence, SL/TP %) WITHOUT touching
the held-out test set, to avoid overfitting to it:

  1. Split the data chronologically: train / validation / test (60/20/20).
  2. For each SL/TP geometry: relabel with THAT geometry (the triple-barrier
     label depends on it) and train the model on the train portion only.
  3. Sweep the volume gate and ML confidence, scoring each combo on the
     VALIDATION portion by profit factor.
  4. Pick the best combo, then report it ONCE on the untouched TEST portion.

This keeps the test result honest: thresholds never saw it. (An earlier version
trained one model on the default-SL/TP label and then traded other SL/TP values
with it — a label/trade mismatch; fixed 2026-09-15, see docs/RESULTS.md Step C.)

Usage: .venv/bin/python scripts/tune_thresholds.py [PAIR] [TIMEFRAME]
"""
import sys
import warnings
from itertools import product
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging  # noqa: E402
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("src.risk_manager").setLevel(logging.ERROR)

from config import settings  # noqa: E402
from src.backtester import Backtester  # noqa: E402
from src.data_handler import DataHandler  # noqa: E402
from src.execution.mock import MockExecutionHandler  # noqa: E402
from src.ml_model import MLModel  # noqa: E402
from src.preprocessor import Preprocessor  # noqa: E402
from src.risk_manager import RiskManager  # noqa: E402
from src.signal_generator import SignalGenerator  # noqa: E402

# Search grid (kept modest so the sweep is quick and not over-fit).
VOLUME_GRID = [1.0, 1.5, 2.0, 2.5]
CONF_GRID = [0.50, 0.55, 0.60, 0.65]
SLTP_GRID = [(0.005, 0.010), (0.005, 0.015), (0.010, 0.020), (0.0075, 0.015)]

# Chronological split boundaries (fractions of rows) and the minimum number of
# validation trades for a combo to count (fewer is not a meaningful sample).
TRAIN_END = 0.60
VAL_END = 0.80
MIN_VAL_TRADES = 5


def _backtest(df, probs, pair, vol_t, conf_t, sl, tp):
    bt = Backtester(
        signal_generator=SignalGenerator(volume_threshold=vol_t, confidence_threshold=conf_t),
        risk_manager=RiskManager(stop_loss_pct=sl, take_profit_pct=tp),
        execution_handler=MockExecutionHandler(
            spread=settings.BACKTEST_SPREAD, slippage=settings.BACKTEST_SLIPPAGE
        ),
        symbol=pair,
    )
    return bt.run(df, probs)


def main() -> None:
    pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"

    df = DataHandler().get_data(pair, tf)
    best = None
    header_printed = False

    for sl, tp in SLTP_GRID:
        # Relabel + retrain for THIS exit geometry (train portion only).
        pre = Preprocessor(sl_pct=sl, tp_pct=tp)
        data = pre.transform(df)
        n = len(data)
        i_tr, i_val = int(n * TRAIN_END), int(n * VAL_END)
        train, val, test = data.iloc[:i_tr], data.iloc[i_tr:i_val], data.iloc[i_val:]
        X_tr, y_tr = pre.features_and_labels(train)
        model = MLModel().tune(
            X_tr, y_tr,
            param_grid=settings.EVAL_PARAM_GRID,
            n_splits=settings.EVAL_CV_SPLITS,
        )
        val_probs = model.predict_proba(pre.features_and_labels(val)[0])
        test_probs = model.predict_proba(pre.features_and_labels(test)[0])
        if not header_printed:
            print(f"\n=== Tuning {pair} {tf} | train={len(train)} val={len(val)} "
                  f"test={len(test)} ===")
            header_printed = True

        # Sweep the gates on VALIDATION only.
        for vol_t, conf_t in product(VOLUME_GRID, CONF_GRID):
            res = _backtest(val, val_probs, pair, vol_t, conf_t, sl, tp)
            if res.n_trades < MIN_VAL_TRADES:
                continue  # ignore combos that barely trade (not meaningful)
            score = res.profit_factor if res.profit_factor != float("inf") else 0
            if best is None or score > best["score"]:
                best = {"score": score, "vol": vol_t, "conf": conf_t, "sl": sl, "tp": tp,
                        "val_pf": res.profit_factor, "val_win": res.win_rate,
                        "val_trades": res.n_trades, "test": test, "test_probs": test_probs}

    if best is None:
        print("No threshold combo produced enough validation trades."); return

    print(f"Best on validation: vol>{best['vol']} conf>{best['conf']} "
          f"SL={best['sl']} TP={best['tp']} "
          f"(val PF={best['val_pf']:.2f} win={best['val_win']:.1%} trades={best['val_trades']})")

    # Report ONCE on the untouched TEST set.
    final = _backtest(best["test"], best["test_probs"], pair,
                      best["vol"], best["conf"], best["sl"], best["tp"])
    print("\n--- FINAL on held-out TEST (thresholds never saw this) ---")
    print(f"  win_rate      : {final.win_rate:.4f}  "
          f"(CI [{final.win_rate_ci_low:.3f}, {final.win_rate_ci_high:.3f}])")
    print(f"  profit_factor : {final.profit_factor:.4f}")
    print(f"  max_drawdown  : {final.max_drawdown:.4f}")
    print(f"  sharpe        : {final.sharpe:.4f}")
    print(f"  net_pnl       : {final.net_pnl:+.2f}")
    print(f"  n_trades      : {final.n_trades}")


if __name__ == "__main__":
    main()
