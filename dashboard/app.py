"""Streamlit dashboard — Module 9 (README §10 step 9).

A web UI to: enter MT5 demo credentials (never hardcoded — §9), tune trading
parameters, run a backtest against the mock engine, and view performance charts.

Run with:
    .venv/bin/python -m streamlit run dashboard/app.py

All heavy logic lives in dashboard/service.py (importable + unit-tested); this
file is just the UI shell.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from config import settings  # noqa: E402
from dashboard import service  # noqa: E402

st.set_page_config(page_title="Automated Trading System", layout="wide")
st.title("📈 Automated Financial Trading System")
st.caption(
    "Hybrid strategy: Volume Z-Score > +1.5 **AND** Random Forest confidence. "
    "Demo account only."
)

# Mode selector — Backtest (mock, no MT5) is the default; Live routes manual
# orders through whichever handler EXECUTION_HANDLER selects (mock = paper).
mode = st.radio(
    "Mode",
    ["Backtest (mock — no MT5 needed)", "Live (paper or MT5 demo)"],
    horizontal=True,
)
LIVE = mode.startswith("Live")

# --------------------------------------------------------------------------- #
# Sidebar — credentials + parameters
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("MT5 Demo Credentials")
    st.caption("Demo account only. Stored only in this session, never committed.")
    # Pre-fill with real creds if set, else the DUMMY_ placeholders (UI demo).
    login = st.text_input(
        "Login ID", value=settings.MT5_LOGIN or settings.DUMMY_MT5_LOGIN
    )
    password = st.text_input(
        "Password",
        value=settings.MT5_PASSWORD or settings.DUMMY_MT5_PASSWORD,
        type="password",
    )
    server = st.text_input(
        "Server", value=settings.MT5_SERVER or settings.DUMMY_MT5_SERVER
    )

    status = service.credentials_status(login, password, server)
    if status["ready"]:
        st.success("Credentials complete (for real MT5 mode).")
    else:
        st.info("Credentials optional — backtesting uses the mock broker.")

    st.divider()
    st.header("Data")
    pair = st.selectbox("Pair", list(settings.PAIRS))
    timeframe = st.selectbox("Timeframe", settings.TIMEFRAMES)

    st.header("Strategy Parameters")
    volume_threshold = st.slider(
        "Volume Z-Score threshold", 0.0, 4.0, float(settings.VOLUME_ZSCORE_THRESHOLD), 0.1
    )
    confidence_threshold = st.slider(
        "ML confidence threshold", 0.50, 0.95, float(settings.ML_CONFIDENCE_THRESHOLD), 0.01
    )
    risk_fraction = st.slider(
        "Risk per trade (%)", 0.5, 5.0, float(settings.RISK_FRACTION_PER_TRADE * 100), 0.5
    ) / 100.0

    run_clicked = st.button("Run Backtest", type="primary")

# --------------------------------------------------------------------------- #
# Main — Backtest mode (default, no MT5) vs Live mode (MT5 demo via RPC)
# --------------------------------------------------------------------------- #
if not LIVE:
    if run_clicked:
        with st.spinner(f"Fetching {pair} {timeframe}, training model, backtesting…"):
            df = service.load_dataset(pair, timeframe)
            train_df, test_df, pre = service.prepare_split(df)
            model = service.train_model(pre, train_df, quick=True)
            result = service.run_backtest(
                pre, model, test_df,
                pair=pair,
                volume_threshold=volume_threshold,
                confidence_threshold=confidence_threshold,
                risk_fraction=risk_fraction,
            )

        st.subheader("Results (with spread + slippage)")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Win Rate", f"{result.win_rate:.1%}", delta="target >60%")
        c2.metric("Max Drawdown", f"{result.max_drawdown:.1%}", delta="target <15%")
        c3.metric("Profit Factor", f"{result.profit_factor:.2f}", delta="target >1.5")
        c4.metric("Sharpe", f"{result.sharpe:.2f}", delta="target >1.0")
        c5.metric("Net P&L", f"{result.net_pnl:+,.2f}")

        targets = result.meets_targets()
        passes = sum(targets.values())
        st.write(f"**Targets met: {passes}/4** "
                 + " ".join(f"{'✅' if v else '❌'} {k}" for k, v in targets.items()))
        st.caption(
            f"Win-rate confidence interval (Wilson, {result.n_trades} trades): "
            f"{result.win_rate_ci_low:.0%}–{result.win_rate_ci_high:.0%}. "
            "Sharpe is per-trade and unannualised."
        )

        st.subheader("Equity Curve")
        st.line_chart(service.equity_curve_frame(result), y="equity")

        st.subheader(f"Trades ({result.n_trades})")
        st.dataframe(service.trades_frame(result), width="stretch")

        if model is not None:
            st.subheader("Feature Importances (model transparency)")
            st.bar_chart(model.feature_importances())
    else:
        st.info("Set parameters in the sidebar and click **Run Backtest**.")

# --------------------------------------------------------------------------- #
# Live mode — manual orders via the configured handler (paper or MT5 demo)
# --------------------------------------------------------------------------- #
else:
    st.subheader("Live order routing — connection status")
    status = service.live_service_status()
    st.caption(
        f"Handler: `{status['handler']}` — set EXECUTION_HANDLER in .env "
        "(mock = paper, remote_mt5 = RPC to the MT5 host, mt5 = direct on Windows)."
    )
    if status["reachable"]:
        st.success(status["detail"])
    else:
        st.warning(status["detail"])

    st.divider()
    st.subheader("Send a manual order (demo only)")
    st.caption(
        "Manual, single-shot — not an auto-trader. Demo account only. Volume is "
        "in lots (the backtest sizes via the RiskManager instead). The paper "
        "handler fills at the reference price; MT5 fills at market."
    )
    oc1, oc2, oc3 = st.columns(3)
    side = oc1.selectbox("Side", ["BUY", "SELL"])
    volume = oc2.number_input("Volume (lots)", min_value=0.01, value=0.10, step=0.01)
    entry = oc3.number_input("Reference price", min_value=0.0, value=1.10, step=0.0001,
                             format="%.5f")
    sl = st.number_input("Stop-loss", min_value=0.0, value=1.09, step=0.0001, format="%.5f")
    tp = st.number_input("Take-profit", min_value=0.0, value=1.12, step=0.0001, format="%.5f")

    if st.button("Send order", type="primary", disabled=not status["reachable"]):
        with st.spinner(f"Sending via {status['handler']}…"):
            res = service.send_live_signal(
                symbol=pair, side=side, volume_lots=volume, sl=sl, tp=tp, price=entry
            )
        if res.get("status") == "error":
            st.error(res["error"])
        else:
            st.success(f"Order result: {res}")
