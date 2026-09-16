"""Win-rate lever sweep: vary TP/SL ratio and measure win rate vs profit factor.

Honest method: the triple-barrier LABEL and the RiskManager BOTH use the same
sl_pct/tp_pct, so changing them keeps training and trading in sync (no leakage).
We retrain per ratio (the label changes) and backtest on the held-out test set,
with the same tuning grid and costs as scripts/run_backtest.py — so a row here
matches a run_backtest.py run with the same SL/TP.

Beyond win rate / PF it prints the realised reward:risk (avg win / avg loss),
the break-even win rate that implies, and the share of trades whose stop was
dynamically tightened (|Volume Z| >= DYNAMIC_SL_ZSCORE_TRIGGER), which is what
makes realised reward:risk differ from nominal.

Usage: .venv/bin/python scripts/sweep_winrate.py [PAIR] [TIMEFRAME]
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import logging  # noqa: E402
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

# (sl_pct, tp_pct) pairs — from "far TP" (Step A) to "close TP" (the default).
RATIOS = [
    (0.005, 0.010),   # far TP: TP 2x SL (Step A)
    (0.006, 0.006),   # symmetric 1:1
    (0.008, 0.006),   # TP closer than SL
    (0.010, 0.005),   # TP half of SL
    (0.012, 0.004),   # close TP (default)
]


def main() -> None:
    pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"
    df = DataHandler().get_data(pair, tf)
    # A trade counts as "tightened" if its stop sits nearer than halfway between
    # the tightened and the normal distance.
    tight_cut = (1 + settings.DYNAMIC_SL_TIGHTEN_FACTOR) / 2

    print(f"\n=== Win-rate sweep: {pair} {tf} ===")
    print(f"{'SL%':>5} {'TP%':>5} {'Win%':>6} {'CI95':>13} {'PF':>5} {'Net':>7} "
          f"{'N':>3} {'DD%':>4} {'Shrp':>5} {'AvgW':>5} {'AvgL':>6} {'R:R':>5} "
          f"{'BE%':>4} {'Tight':>5}")

    for sl, tp in RATIOS:
        # Relabel + retrain for THIS ratio (label depends on sl/tp).
        pre = Preprocessor(sl_pct=sl, tp_pct=tp)
        data = pre.transform(df)
        train, test = pre.chronological_split(data)
        X_tr, y_tr = pre.features_and_labels(train)
        model = MLModel().tune(
            X_tr, y_tr,
            param_grid=settings.EVAL_PARAM_GRID,
            n_splits=settings.EVAL_CV_SPLITS,
        )
        probs = model.predict_proba(pre.features_and_labels(test)[0])
        bt = Backtester(
            signal_generator=SignalGenerator(),
            risk_manager=RiskManager(stop_loss_pct=sl, take_profit_pct=tp),
            execution_handler=MockExecutionHandler(
                spread=settings.BACKTEST_SPREAD, slippage=settings.BACKTEST_SLIPPAGE
            ),
            symbol=pair,
        )
        r = bt.run(test, probs)
        pf = r.profit_factor if r.profit_factor != float("inf") else 99.9
        if r.trades:
            tr = pd.DataFrame(r.trades)
            avg_w = tr.loc[tr.pnl > 0, "pnl"].mean()
            avg_l = tr.loc[tr.pnl < 0, "pnl"].mean()
            rr = avg_w / abs(avg_l) if avg_l < 0 else float("nan")
            be = abs(avg_l) / (avg_w + abs(avg_l)) if avg_l < 0 else float("nan")
            stop_dist = (tr["price"] - tr["sl"]).abs() / tr["price"]
            tight = (stop_dist < sl * tight_cut).mean()
        else:
            avg_w = avg_l = rr = be = tight = float("nan")
        print(f"{sl*100:>5.1f} {tp*100:>5.1f} {r.win_rate*100:>5.1f}% "
              f"[{r.win_rate_ci_low*100:>4.1f},{r.win_rate_ci_high*100:>5.1f}] "
              f"{pf:>5.2f} {r.net_pnl:>+7.0f} {r.n_trades:>3} {r.max_drawdown*100:>4.1f} "
              f"{r.sharpe:>5.2f} {avg_w:>5.0f} {avg_l:>6.0f} {rr:>5.2f} "
              f"{be*100:>4.0f} {tight:>5.0%}")


if __name__ == "__main__":
    main()
