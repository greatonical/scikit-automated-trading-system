"""No-skill baseline — how much of the win rate is the model, how much the exits?

Trains the model exactly as scripts/run_backtest.py does, then backtests the SAME
held-out window with the SAME exits, costs and volume gate, but with the ML
direction replaced by:
  * always BUY on every volume-gated bar,
  * always SELL on every volume-gated bar (skipped when ALLOW_SHORTS=false),
  * a random direction per bar (N_SEEDS seeds; mean and range reported).

If the model's win rate sits inside the random-direction range, the win rate is
explained by the exit geometry, not by prediction skill — compare profit factor
instead. With a close take-profit and a wide stop, most random entries "win".

Usage: .venv/bin/python scripts/baseline_noskill.py [PAIR] [TIMEFRAME]
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import logging  # noqa: E402
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("src.risk_manager").setLevel(logging.ERROR)

import numpy as np  # noqa: E402

from config import settings  # noqa: E402
from src.backtester import Backtester  # noqa: E402
from src.data_handler import DataHandler  # noqa: E402
from src.execution.mock import MockExecutionHandler  # noqa: E402
from src.ml_model import MLModel  # noqa: E402
from src.preprocessor import Preprocessor  # noqa: E402
from src.risk_manager import RiskManager  # noqa: E402
from src.signal_generator import SignalGenerator  # noqa: E402

N_SEEDS = 20   # random-direction runs
SEED = 0       # base seed, so the baseline itself is reproducible


def _run(pair, test, probs):
    return Backtester(
        signal_generator=SignalGenerator(),
        risk_manager=RiskManager(),
        execution_handler=MockExecutionHandler(
            spread=settings.BACKTEST_SPREAD, slippage=settings.BACKTEST_SLIPPAGE
        ),
        symbol=pair,
    ).run(test, probs)


def _row(name, r):
    pf = r.profit_factor if r.profit_factor != float("inf") else 99.9
    print(f"  {name:22} win {r.win_rate:6.1%} [{r.win_rate_ci_low:5.1%}, "
          f"{r.win_rate_ci_high:5.1%}]  PF {pf:5.2f}  net {r.net_pnl:+8.2f}  "
          f"trades {r.n_trades}")


def main() -> None:
    pair = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1h"

    df = DataHandler().get_data(pair, tf)
    pre = Preprocessor()
    train, test = pre.chronological_split(pre.transform(df))
    X_tr, y_tr = pre.features_and_labels(train)
    model = MLModel().tune(
        X_tr, y_tr,
        param_grid=settings.EVAL_PARAM_GRID,
        n_splits=settings.EVAL_CV_SPLITS,
    )
    probs = model.predict_proba(pre.features_and_labels(test)[0])

    print(f"\n=== No-skill baseline: {pair} {tf} | SL {settings.DEFAULT_STOP_LOSS_PCT:.2%} "
          f"TP {settings.DEFAULT_TAKE_PROFIT_PCT:.2%} | same exits, costs, volume gate ===")
    m = _run(pair, test, probs)
    _row("model (RF direction)", m)
    # P=1.0 passes any bullish threshold; P=0.0 passes the bearish side.
    _row("always BUY", _run(pair, test, np.ones(len(test))))
    if settings.ALLOW_SHORTS:
        _row("always SELL", _run(pair, test, np.zeros(len(test))))

    rng = np.random.default_rng(SEED)
    rand = [_run(pair, test, rng.choice([0.0, 1.0], size=len(test)))
            for _ in range(N_SEEDS)]
    wins = np.array([r.win_rate for r in rand])
    pfs = np.array([min(r.profit_factor, 99.9) for r in rand])
    print(f"  random direction x{N_SEEDS:<4}  win mean {wins.mean():6.1%} "
          f"(range {wins.min():.1%}–{wins.max():.1%})  PF mean {pfs.mean():.2f} "
          f"(range {pfs.min():.2f}–{pfs.max():.2f})  "
          f"trades ~{np.mean([r.n_trades for r in rand]):.0f}")
    print(f"  model win rate >= random in {np.mean(m.win_rate >= wins):.0%} of seeds; "
          f"model PF >= random in {np.mean(m.profit_factor >= pfs):.0%} of seeds")


if __name__ == "__main__":
    main()
