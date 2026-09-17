"""Live signal -> order session on a DEMO account (Module 12 / README §13).

This is the only path in the project where a trade is produced end-to-end by the
system itself, rather than by a human typing an order into the dashboard:

    DataHandler -> Preprocessor (features only) -> MLModel -> SignalGenerator
    (volume gate AND ML gate) -> RiskManager (fixed-fractional size + stops)
    -> ExecutionHandler (mock | remote_mt5 | mt5)

That distinction is the whole point: a trade placed by hand proves nothing about
the strategy, whereas a trade whose side, size, stop and target were all chosen by
the model and the gates is genuine evidence for report objective 4.

Two implementation notes that are easy to get wrong:

1. **Not** ``Preprocessor.transform()``. transform() appends the triple-barrier
   label and then drops every row whose Target is NaN — which is precisely the
   newest bar, the one we want to trade. (Only that bar: the labeller truncates
   its forward window at the end of the data and falls back to "close vs entry",
   so every earlier bar still gets a label. Measured on the cached EUR/USD 1h
   window: transform() ends at 20:00, this path ends at 21:00.) Live inference
   needs features without labels, so this module builds them with add_zscores +
   add_indicators and drops NaNs on the feature columns alone.

2. **Never ``force_refresh=True``.** That would rewrite data/*_1h.parquet, shifting
   the cached window every documented result depends on. We pass ``use_cache=False``
   instead: fetch fresh data for the decision, write nothing to disk.

Safety: DRY RUN by default — it prints the decision and writes the session log but
sends no order. Pass --send to actually trade. Demo accounts only (README §9); the
handler is whatever EXECUTION_HANDLER selects, which is ``mock`` (paper) unless you
changed it.

Usage:
    .venv/bin/python scripts/live_session.py EURUSD 1h                  # dry run, one check
    .venv/bin/python scripts/live_session.py EURUSD 1h --send           # trade if a signal fires
    .venv/bin/python scripts/live_session.py EURUSD 1h --send --loop    # run each bar close
    .venv/bin/python scripts/live_session.py EURUSD 1h --send --equity 5000
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from config import settings  # noqa: E402
from src.data_handler import DataHandler  # noqa: E402
from src.execution.factory import get_execution_handler  # noqa: E402
from src.ml_model import MLModel  # noqa: E402
from src.preprocessor import Preprocessor  # noqa: E402
from src.risk_manager import RiskManager  # noqa: E402
from src.signal_generator import Action, SignalGenerator  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

BAR_SECONDS = {"1h": 3600, "4h": 4 * 3600}
BAR_CLOSE_BUFFER_S = 30  # let the provider publish the closed bar before asking


# --------------------------------------------------------------------------- #
# Features for the CURRENT bar (no labels — see module docstring)
# --------------------------------------------------------------------------- #
def live_features(pre: Preprocessor, df: pd.DataFrame) -> pd.DataFrame:
    """Z-scores + indicators, keeping the most recent bar.

    Mirrors Preprocessor.transform() except that it never calls add_labels(), so
    the trailing bars that have no resolved Target are retained.
    """
    work = pre.add_indicators(pre.add_zscores(df.sort_index()))
    missing = [c for c in pre.feature_columns if c not in work.columns]
    if missing:
        raise KeyError(f"Missing feature columns after indicators: {missing}")
    return work.dropna(subset=pre.feature_columns)


def model_path_for(pair: str, timeframe: str) -> Path:
    return settings.MODELS_DIR / settings.MODEL_FILENAME_TEMPLATE.format(
        pair=pair, timeframe=timeframe
    )


def load_model(pair: str, timeframe: str) -> MLModel:
    path = model_path_for(pair, timeframe)
    if not path.exists():
        raise SystemExit(
            f"No trained model at {path}.\n"
            f"Train one first:  .venv/bin/python scripts/run_backtest.py {pair} {timeframe}"
        )
    model = MLModel.load(path)
    meta = getattr(model, "metadata", None) or {}
    if meta.get("pair") not in (None, pair) or meta.get("timeframe") not in (None, timeframe):
        print(f"  ! WARNING: model was trained on {meta.get('pair')} {meta.get('timeframe')}, "
              f"running on {pair} {timeframe}")
    return model


# --------------------------------------------------------------------------- #
# Session log (JSONL — one record per check, appended)
# --------------------------------------------------------------------------- #
def log_path_for(pair: str, timeframe: str) -> Path:
    d = ROOT / "logs"
    d.mkdir(exist_ok=True)
    return d / f"live_session_{pair}_{timeframe}.jsonl"


def append_log(path: Path, record: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def already_traded_bar(path: Path, bar_time: str) -> bool:
    """True if an order was already SENT for this bar (restart-safe de-duplication)."""
    if not path.exists():
        return False
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("order_sent") and str(rec.get("bar_time")) == str(bar_time):
            return True
    return False


# --------------------------------------------------------------------------- #
# One decision cycle
# --------------------------------------------------------------------------- #
def run_once(
    pair: str,
    timeframe: str,
    *,
    model: MLModel,
    pre: Preprocessor,
    sg: SignalGenerator,
    rm: RiskManager,
    send: bool,
    log_path: Path,
) -> dict:
    """Fetch -> score -> decide -> (optionally) place one order. Returns the record."""
    checked_at = datetime.now(timezone.utc)

    # use_cache=False: fresh data for the decision, and the research cache is left
    # untouched so every documented backtest number stays reproducible.
    df = DataHandler().get_data(pair, timeframe, use_cache=False)
    feats = live_features(pre, df)
    if feats.empty:
        rec = {"checked_at_utc": checked_at, "pair": pair, "timeframe": timeframe,
               "error": "no usable bars after feature construction"}
        append_log(log_path, rec)
        return rec

    bar = feats.iloc[-1]
    bar_time = feats.index[-1]
    X = feats[pre.feature_columns].iloc[[-1]]

    probability = float(model.predict_proba(X)[0])
    volume_z = float(bar["ZScore_Volume"])
    close = float(bar["Close"])

    signal = sg.decide(probability, volume_z, bar_time)

    rec: dict = {
        "checked_at_utc": checked_at,
        "bar_time": bar_time,
        "pair": pair,
        "timeframe": timeframe,
        "close": close,
        "probability": round(probability, 4),
        "volume_zscore": round(volume_z, 4),
        "rule_pass": signal.rule_pass,
        "ml_pass": signal.ml_pass,
        "action": signal.action.value,
        "handler": settings.EXECUTION_HANDLER,
        "order_sent": False,
    }

    print(f"\n[{checked_at:%Y-%m-%d %H:%M:%S} UTC] {pair} {timeframe}  bar {bar_time}")
    print(f"  close={close:.5f}  P(bull)={probability:.3f}  volZ={volume_z:+.3f}")
    print(f"  volume gate (> {sg.volume_threshold}): {'PASS' if signal.rule_pass else 'fail'}"
          f"   |   ML gate (> {sg.confidence_threshold}): {'PASS' if signal.ml_pass else 'fail'}"
          f"   ->  {signal.action.value}")

    if signal.action is Action.HOLD:
        append_log(log_path, rec)
        return rec

    if not rm.can_trade():
        rec["skipped"] = "risk limit reached (drawdown or daily loss)"
        print(f"  ! skipped: {rec['skipped']}")
        append_log(log_path, rec)
        return rec

    if already_traded_bar(log_path, bar_time):
        rec["skipped"] = "an order was already sent for this bar"
        print(f"  ! skipped: {rec['skipped']}")
        append_log(log_path, rec)
        return rec

    plan = rm.size_position(signal.action.value, close, volume_zscore=volume_z)
    lots = plan.volume / settings.FX_STANDARD_LOT_UNITS
    rec.update({
        "side": plan.side,
        "units": round(plan.volume, 2),
        "lots": round(lots, 4),
        "entry_reference": round(plan.entry_price, 5),
        "stop_loss": round(plan.stop_loss, 5),
        "take_profit": round(plan.take_profit, 5),
        "risk_amount": round(plan.risk_amount, 2),
        "equity_assumed": rm.equity,
    })
    print(f"  plan: {plan.side} {plan.volume:,.0f} units ({lots:.2f} lots)  "
          f"SL {plan.stop_loss:.5f}  TP {plan.take_profit:.5f}  risking {plan.risk_amount:.2f}")

    if not send:
        rec["dry_run"] = True
        print("  DRY RUN — nothing sent. Re-run with --send to place this order.")
        append_log(log_path, rec)
        return rec

    handler = get_execution_handler()
    handler.connect()
    start = time.perf_counter()
    result = handler.place_order(
        pair, plan.side, plan.volume, plan.stop_loss, plan.take_profit, price=close
    )
    latency_ms = round((time.perf_counter() - start) * 1000, 1)

    rec["order_sent"] = True
    rec["latency_ms"] = latency_ms
    rec["meets_latency_target"] = latency_ms < settings.TARGET_LATENCY_MS
    for key in ("ticket", "status", "price", "retcode", "reason", "lots", "hint"):
        if key in result:
            rec[f"broker_{key}"] = result[key]

    print(f"  SENT -> status={result.get('status')} ticket={result.get('ticket')} "
          f"fill={result.get('price')} latency={latency_ms} ms "
          f"({'within' if rec['meets_latency_target'] else 'OVER'} "
          f"the {settings.TARGET_LATENCY_MS} ms target)")
    if result.get("status") != "filled":
        print(f"  ! rejected: {result.get('reason') or result.get('retcode')} "
              f"{result.get('hint', '')}")

    append_log(log_path, rec)
    return rec


def seconds_to_next_bar(timeframe: str) -> float:
    """Seconds until the next bar closes (plus a small publication buffer)."""
    period = BAR_SECONDS[timeframe]
    now = time.time()
    return (period - (now % period)) + BAR_CLOSE_BUFFER_S


def main() -> None:
    ap = argparse.ArgumentParser(description="Live signal -> order session (demo only).")
    ap.add_argument("pair", nargs="?", default="EURUSD")
    ap.add_argument("timeframe", nargs="?", default="1h", choices=sorted(BAR_SECONDS))
    ap.add_argument("--send", action="store_true",
                    help="actually place orders (default: dry run)")
    ap.add_argument("--loop", action="store_true",
                    help="keep running, re-checking at each bar close")
    ap.add_argument("--equity", type=float, default=settings.STARTING_EQUITY,
                    help="account equity used for position sizing "
                         f"(default {settings.STARTING_EQUITY:,.0f}); set this to the "
                         "demo account's real balance")
    ap.add_argument("--max-trades", type=int, default=5,
                    help="stop after this many orders in one session (default 5)")
    args = ap.parse_args()

    pre = Preprocessor()
    model = load_model(args.pair, args.timeframe)
    sg = SignalGenerator()
    rm = RiskManager(starting_equity=args.equity)
    log_path = log_path_for(args.pair, args.timeframe)

    print(f"=== Live session: {args.pair} {args.timeframe} ===")
    print(f"  handler        : {settings.EXECUTION_HANDLER}"
          f"{'  (paper — no broker involved)' if settings.EXECUTION_HANDLER == 'mock' else ''}")
    print(f"  mode           : {'SEND ORDERS' if args.send else 'DRY RUN'}")
    print(f"  equity assumed : {args.equity:,.2f}   risk/trade: {rm.risk_fraction:.1%}")
    print(f"  gates          : volume Z > {sg.volume_threshold}  AND  P(bull) > {sg.confidence_threshold}")
    print(f"  model          : {model_path_for(args.pair, args.timeframe).name}")
    print(f"  session log    : {log_path.relative_to(ROOT)}")
    if args.send and settings.EXECUTION_HANDLER != "mock":
        print("  *** DEMO ACCOUNTS ONLY — never point this at a funded account. ***")

    sent = 0
    try:
        while True:
            rec = run_once(
                args.pair, args.timeframe, model=model, pre=pre, sg=sg, rm=rm,
                send=args.send, log_path=log_path,
            )
            sent += int(bool(rec.get("order_sent")))
            if sent >= args.max_trades:
                print(f"\nReached --max-trades ({args.max_trades}); stopping.")
                break
            if not args.loop:
                break
            wait = seconds_to_next_bar(args.timeframe)
            print(f"  ... next check in {wait/60:.1f} min (at the next {args.timeframe} close)")
            time.sleep(wait)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    print(f"\nOrders sent this session: {sent}. Log: {log_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
