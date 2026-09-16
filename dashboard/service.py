"""Dashboard service layer (Module 9 helper).

All the dashboard's logic lives here — pure functions with no Streamlit imports —
so it can be unit-tested on macOS without launching a browser. `app.py` is a thin
UI shell that calls into this module.
"""
from __future__ import annotations

import time

import pandas as pd

from config import settings
from src.backtester import Backtester
from src.data_handler import DataHandler
from src.execution.factory import get_execution_handler
from src.execution.mock import MockExecutionHandler
from src.ml_model import MLModel
from src.preprocessor import Preprocessor
from src.risk_manager import RiskManager
from src.signal_generator import SignalGenerator


def load_dataset(pair: str, timeframe: str) -> pd.DataFrame:
    """Fetch (cached) OHLCV for a pair/timeframe."""
    return DataHandler().get_data(pair, timeframe)


def prepare_split(df: pd.DataFrame):
    """Transform + chronological split -> (train_df, test_df, pre)."""
    pre = Preprocessor()
    transformed = pre.transform(df)
    train_df, test_df = pre.chronological_split(transformed)
    return train_df, test_df, pre


def train_model(pre: Preprocessor, train_df: pd.DataFrame, quick: bool = True) -> MLModel:
    """Train (and tune) a model on the training split only.

    quick=True uses the evaluation grid shared with scripts/run_backtest.py, so
    the dashboard reproduces the documented numbers; quick=False uses the full
    config grid (much slower).
    """
    X_train, y_train = pre.features_and_labels(train_df)
    if quick:
        grid, splits = settings.EVAL_PARAM_GRID, settings.EVAL_CV_SPLITS
    else:
        grid, splits = settings.RF_PARAM_GRID, settings.CV_N_SPLITS
    return MLModel().tune(X_train, y_train, param_grid=grid, n_splits=splits)


def run_backtest(
    pre: Preprocessor,
    model: MLModel,
    test_df: pd.DataFrame,
    *,
    pair: str,
    volume_threshold: float,
    confidence_threshold: float,
    risk_fraction: float,
    spread: float | None = None,
    slippage: float | None = None,
):
    """Run a backtest with UI-supplied parameters; return a BacktestResult."""
    X_test, _ = pre.features_and_labels(test_df)
    probs = model.predict_proba(X_test)

    bt = Backtester(
        signal_generator=SignalGenerator(
            volume_threshold=volume_threshold,
            confidence_threshold=confidence_threshold,
        ),
        risk_manager=RiskManager(risk_fraction=risk_fraction),
        execution_handler=MockExecutionHandler(
            spread=settings.BACKTEST_SPREAD if spread is None else spread,
            slippage=settings.BACKTEST_SLIPPAGE if slippage is None else slippage,
        ),
        symbol=pair,
    )
    return bt.run(test_df, probs)


# --------------------------------------------------------------------------- #
# Live order routing — whichever handler EXECUTION_HANDLER selects
# --------------------------------------------------------------------------- #
def _live_handler(handler: str | None, host: str | None, port: int | None,
                  timeout: float):
    """Build the live order-routing handler via the factory (one config switch)."""
    name = (handler or settings.EXECUTION_HANDLER).lower()
    kwargs = (
        {"host": host, "port": port, "timeout": timeout}
        if name == "remote_mt5" else {}
    )
    return name, get_execution_handler(name, **kwargs)


def live_service_status(
    host: str | None = None, port: int | None = None, handler: str | None = None,
) -> dict:
    """Is the live order route usable? (for the Live tab)

    Never raises — returns {"handler", "reachable", "detail"} so the dashboard can
    show a friendly status instead of crashing when MT5 isn't running.
    """
    try:
        name, client = _live_handler(handler, host, port, timeout=2.0)
    except ValueError as exc:  # unknown handler name
        return {"handler": handler or settings.EXECUTION_HANDLER,
                "reachable": False, "detail": str(exc)}

    if name == "mock":
        return {
            "handler": name, "reachable": True,
            "detail": (
                "Paper mode (EXECUTION_HANDLER=mock): orders fill in the in-process "
                "simulated broker at the reference price — no MT5 involved. Set "
                "EXECUTION_HANDLER=remote_mt5 to route orders to the MT5 host."
            ),
        }
    if name == "remote_mt5":
        if client.ping():
            return {"handler": name, "reachable": True,
                    "detail": f"Connected to MT5 RPC service at {client.host}:{client.port}"}
        return {
            "handler": name, "reachable": False,
            "detail": (
                f"MT5 RPC service unreachable at {client.host}:{client.port}. Start it "
                "on the Windows MT5 host (`python -m src.execution.mt5_service`; see "
                "docs/WINE_VERDICT.md). Backtesting still works without it."
            ),
        }
    # "mt5": direct MetaTrader5 — only works on the Windows host itself.
    try:
        client.connect()
        client.disconnect()
        return {"handler": name, "reachable": True,
                "detail": "Connected directly to the local MT5 terminal."}
    except RuntimeError as exc:
        return {"handler": name, "reachable": False, "detail": str(exc)}


def send_live_signal(
    *, symbol: str, side: str, volume_lots: float, sl: float, tp: float,
    price: float | None = None,
    host: str | None = None, port: int | None = None, handler: str | None = None,
) -> dict:
    """Send one manual order via the configured live handler (demo only).

    ``volume_lots`` is converted to units — the engine's volume convention — and
    the MT5 handler converts back to broker lots using the symbol's real contract
    size. ``price`` is the reference price: the paper (mock) handler fills at it;
    MT5 ignores it and fills at market.

    Returns the handler's result dict plus ``latency_ms`` (wall-clock time of the
    place_order call: signal -> fill confirmation), or an error dict.
    """
    units = volume_lots * settings.FX_STANDARD_LOT_UNITS
    try:
        _, client = _live_handler(handler, host, port, timeout=10.0)
        client.connect()
        start = time.perf_counter()
        res = client.place_order(symbol, side, units, sl, tp, price=price)
        res["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return res
    except (ConnectionError, RuntimeError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}


def credentials_status(login: str, password: str, server: str) -> dict:
    """Report whether MT5 demo credentials are present (never logs the values).

    Used by the UI to show a connection-readiness indicator. We never store or
    print the actual password — only whether each field is filled.
    """
    return {
        "login_set": bool(login),
        "password_set": bool(password),
        "server_set": bool(server),
        "ready": bool(login and password and server),
    }


def equity_curve_frame(result) -> pd.DataFrame:
    """BacktestResult.equity_curve -> a tidy DataFrame for charting."""
    return pd.DataFrame({"equity": result.equity_curve})


def trades_frame(result) -> pd.DataFrame:
    """BacktestResult.trades -> a DataFrame (empty-safe) for the trade table."""
    cols = ["ticket", "entry_time", "exit_time", "side", "price", "exit_price",
            "pnl", "exit_reason", "bars_held"]
    if not result.trades:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(result.trades)
    return df[[c for c in cols if c in df.columns]]
