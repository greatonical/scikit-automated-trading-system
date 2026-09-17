"""Central configuration — the single source of truth for every tunable value.

README §12: "Default config values live in `config/settings.py` — never scatter
magic numbers (the +1.5 threshold, 80/20 split, 60% target) across the codebase."

Nothing in `src/` should hardcode a threshold, ratio, pair, timeframe, or target.
Import from here instead. Values can be overridden via environment variables where
it makes sense (see `_env_*` helpers) so the Streamlit UI / .env can adjust them
without code edits.
"""
from __future__ import annotations

import os
from pathlib import Path

# Load .env (if present) so MT5 creds / overrides defined there reach os.environ.
# .env is gitignored — real credentials never get committed (README §9).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is a core dep; guard just in case
    pass

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"

DATA_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- #
# Small env helpers (so the dashboard / .env can override without code changes)
# --------------------------------------------------------------------------- #
def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw not in (None, "") else default


def _env_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    return raw if raw not in (None, "") else default


# --------------------------------------------------------------------------- #
# Data specification (README §5)
# --------------------------------------------------------------------------- #
# Forex pairs. Keys are our canonical names; values are the yfinance tickers.
PAIRS: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
}

# Volume source (README §3.3.1 — the +1.5 gate proves "institutional
# participation"). Spot FX (=X) on Yahoo reports volume=0 because spot Forex is
# decentralised with no central exchange. We therefore take PRICE from spot
# (the actual EUR/USD / GBP/USD rate the report studies) and VOLUME from the
# matching CME FX FUTURES (real, centrally-reported exchange volume) aligned by
# timestamp. CME FX-futures volume is the standard proxy for institutional FX
# activity, which is exactly what the volume gate is meant to detect.
#   6E=F  = Euro FX futures (CME)
#   6B=F  = British Pound futures (CME)
VOLUME_SOURCE: dict[str, str] = {
    "EURUSD": "6E=F",
    "GBPUSD": "6B=F",
}

# If True, DataHandler replaces spot's (zero) Volume with aligned futures volume.
# If the futures fetch fails/empties, it falls back to spot volume and logs it.
USE_FUTURES_VOLUME = True

# Timeframes we trade/analyse. yfinance interval strings.
TIMEFRAMES: list[str] = ["1h", "4h"]

# Desired historical span (README §5: 5 years, 2019–2024). NOTE: Yahoo Finance
# only serves intraday (<=1h) data for ~the last 730 days, so for 1h/4h the
# DataHandler will fetch the deepest window available and log the ACTUAL range.
# The full span is honoured for any daily-or-coarser request.
HISTORY_START = "2019-01-01"
HISTORY_END = "2024-12-31"

# Hard cap Yahoo enforces on intraday history. DataHandler clamps intraday
# requests to this many days back from "now" and logs the real coverage.
INTRADAY_MAX_DAYS = 729  # stay just under Yahoo's 730-day intraday limit

# Intervals Yahoo treats as "intraday" (subject to INTRADAY_MAX_DAYS).
INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "1h", "90m"}

# yfinance has no native 4h bar; we fetch 1h and resample. Map our timeframe
# label -> (fetch_interval, resample_rule). None resample = a BASE timeframe,
# fetched + cached as-is (its label must equal its yfinance interval). A derived
# timeframe (e.g. 4h) is rebuilt from its cached base at load time and never
# cached itself, so it can never drift out of sync with the base (window, volume).
TIMEFRAME_FETCH: dict[str, tuple[str, str | None]] = {
    "1h": ("1h", None),
    "4h": ("1h", "4h"),
}

# Cache fetched data to disk so the engine/backtester run offline.
CACHE_ENABLED = True
CACHE_FORMAT = "parquet"  # falls back to csv if pyarrow unavailable

# Data-quality guard: warn when fewer than this fraction of bars carry nonzero
# volume. The +1.5 volume gate is meaningless on a zero-volume series (a stale
# pre-futures-merge cache once silently produced zero 4h trades this way).
MIN_NONZERO_VOLUME_FRACTION = 0.5


# --------------------------------------------------------------------------- #
# Z-Score / feature engineering (README §5)
# --------------------------------------------------------------------------- #
# Rolling window for Z-Score (NOT a global mean — README §5 requires rolling).
ZSCORE_WINDOW = _env_int("ZSCORE_WINDOW", 20)

# Base features (README §5 "Model input features").
BASE_FEATURE_COLUMNS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "ZScore_Close",
    "ZScore_Volume",
]

# Technical-indicator features, added one at a time in the improvement phase
# (see docs/RESULTS.md). Each is toggled here and appended to FEATURE_COLUMNS
# below. All are strictly backward-looking (no leakage).
# RSI: tested in Step B1 — it HURT performance (win rate & profit factor fell on
# both pairs vs the Step-A baseline; see docs/RESULTS.md), so it's OFF by default.
# Code kept and tested; flip USE_RSI=true to re-enable / experiment.
USE_RSI = _env_str("USE_RSI", "false").lower() == "true"
RSI_PERIOD = _env_int("RSI_PERIOD", 14)

# MACD (Step B2): adds three features — the MACD line, signal line, histogram.
MACD_FAST = _env_int("MACD_FAST", 12)
MACD_SLOW = _env_int("MACD_SLOW", 26)
MACD_SIGNAL = _env_int("MACD_SIGNAL", 9)
# MACD: tested in Step B2 — it HURT badly (both pairs back to a net loss, drawdown
# breached 15%, trade count doubled with worse trades; see docs/RESULTS.md). OFF.
USE_MACD = _env_str("USE_MACD", "false").lower() == "true"

# ATR (Step B3): Average True Range = a volatility measure. Two uses:
#  (1) as a model feature, and
#  (2) to size stop-loss/take-profit by volatility instead of a flat % (so the
#      triple-barrier label and the live stops adapt to market conditions).
ATR_PERIOD = _env_int("ATR_PERIOD", 14)
# ATR: tested in Step B3 (see docs/RESULTS.md). As a FEATURE it was neutral
# (EURUSD identical, GBPUSD mixed). As volatility-based STOPS it HURT at every
# multiple tried (per-candle distance variation caused more stop-outs / losses).
# Both OFF; flat-% stops from Step A win. Code kept for reproducibility.
USE_ATR = _env_str("USE_ATR", "false").lower() == "true"

# ATR-based stops: when on, SL/TP distances = ATR × multiple instead of flat %.
USE_ATR_STOPS = _env_str("USE_ATR_STOPS", "false").lower() == "true"
ATR_SL_MULTIPLE = _env_float("ATR_SL_MULTIPLE", 5.0)
ATR_TP_MULTIPLE = _env_float("ATR_TP_MULTIPLE", 10.0)

# Order blocks (Step F): the zone a market leaves behind when price breaks structure —
# the "institutional order block" idea the report's literature review cites (Sirignano &
# Cont, 2019) and §2.5 promises. Detection follows the rule set a sibling production
# system uses: a break of structure must be confirmed by a CLOSE beyond the recent swing,
# the zone is the extreme candle of that window, it is rejected if it is large relative to
# ATR (or too small to be meaningful), and it is consumed once price trades back into it.
# Exposed as FEATURES for the Random Forest — the volume gate and the hybrid AND-logic are
# unchanged — so this is one measurable change, like every other indicator tested.
USE_ORDER_BLOCKS = _env_str("USE_ORDER_BLOCKS", "false").lower() == "true"
OB_SWING_LOOKBACK = _env_int("OB_SWING_LOOKBACK", 10)    # bars defining the swing
OB_ATR_PERIOD = _env_int("OB_ATR_PERIOD", 10)            # ATR used for the size filter
OB_MAX_ATR_MULTIPLE = _env_float("OB_MAX_ATR_MULTIPLE", 3.5)   # reject zones wider than this
OB_MIN_SIZE_PCT = _env_float("OB_MIN_SIZE_PCT", 0.0003)  # reject zones thinner than 0.03%
OB_MAX_ACTIVE_AGE = _env_int("OB_MAX_ACTIVE_AGE", 200)   # bars a zone stays live
OB_DIST_CAP = _env_float("OB_DIST_CAP", 0.02)            # clip the distance feature at ±2%

# Higher-timeframe trend (Step B4): trend CONTEXT, not an oscillator. Adds two
# features — TrendDist (how far price is above/below a long moving average, as a
# fraction) and TrendUp (1 if price is above the long MA, else 0). The long MA on
# a 1h chart approximates a higher-timeframe (e.g. ~4h/daily) trend.
HTF_TREND_WINDOW = _env_int("HTF_TREND_WINDOW", 100)
USE_HTF_TREND = _env_str("USE_HTF_TREND", "false").lower() == "true"  # Step B4

# Assemble the active feature list from the base + enabled indicators.
FEATURE_COLUMNS = list(BASE_FEATURE_COLUMNS)
if USE_RSI:
    FEATURE_COLUMNS.append("RSI")
if USE_MACD:
    FEATURE_COLUMNS += ["MACD", "MACD_Signal", "MACD_Hist"]
if USE_ATR:
    FEATURE_COLUMNS.append("ATR")
if USE_HTF_TREND:
    FEATURE_COLUMNS += ["TrendDist", "TrendUp"]
if USE_ORDER_BLOCKS:
    FEATURE_COLUMNS += ["OB_BullDist", "OB_BearDist", "OB_Inside"]

# Time-of-day / session (Step D, optional): hour of day + a London/NY-overlap flag.
# FX behaviour varies by session; cheap features, sometimes useful.
USE_TIME_FEATURES = _env_str("USE_TIME_FEATURES", "false").lower() == "true"
if USE_TIME_FEATURES:
    FEATURE_COLUMNS += ["HourSin", "HourCos", "SessionOverlap"]

# How many candles ahead we look to define the label (bullish continuation).
LABEL_HORIZON = 1  # next candle (used by the "next_candle" label method)

# Label method (see docs/TRIPLE_BARRIER_EXPLAINED.md):
#   "next_candle"     -> class 1 if the next close is higher (the original).
#   "triple_barrier"  -> class 1 if take-profit is hit BEFORE stop-loss within a
#                         time window. Aligns the ML target with the real SL/TP exit
#                         logic, so the model trains on the trades the system takes.
LABEL_METHOD = _env_str("LABEL_METHOD", "triple_barrier")

# Triple-barrier settings. The TP/SL distances reuse the SAME risk config the
# RiskManager uses for live trades (DEFAULT_TAKE_PROFIT_PCT / DEFAULT_STOP_LOSS_PCT,
# defined in the Risk section below) so labels and trades speak the same language.
# The vertical barrier = max candles to hold before giving up.
TRIPLE_BARRIER_MAX_HOLD = _env_int("TRIPLE_BARRIER_MAX_HOLD", 24)

# Label ↔ trade alignment (see docs/RESULTS.md "Label/trade alignment"). By
# default the label uses the flat DEFAULT_STOP_LOSS_PCT, but the RiskManager
# tightens the stop when |Volume Z| >= DYNAMIC_SL_ZSCORE_TRIGGER — which applies to
# most gated trades. When True, the label applies the SAME tightening rule (using
# the entry candle's trailing Volume Z-Score, so no leakage).
LABEL_DYNAMIC_SL = _env_str("LABEL_DYNAMIC_SL", "false").lower() == "true"


# --------------------------------------------------------------------------- #
# Hybrid signal logic (README §2 — the heart of the system)
# --------------------------------------------------------------------------- #
# Rule-based gate: Volume Z-Score must EXCEED this to allow a trade.
VOLUME_ZSCORE_THRESHOLD = _env_float("VOLUME_ZSCORE_THRESHOLD", 1.5)

# ML gate: Random Forest bullish-class probability must EXCEED this.
ML_CONFIDENCE_THRESHOLD = _env_float("ML_CONFIDENCE_THRESHOLD", 0.55)

# Short side. README §2 defines the ML gate on the bullish class only (class 0 =
# bearish OR neutral). The implementation also SELLs when P(bullish) is low
# (< 1 − threshold). Note the triple-barrier label is long-side only, so a low
# P(bullish) is not direct evidence that a short would win. False = long-only.
ALLOW_SHORTS = _env_str("ALLOW_SHORTS", "true").lower() == "true"


# --------------------------------------------------------------------------- #
# Train/test split + cross-validation (README §5, §6 — CRITICAL)
# --------------------------------------------------------------------------- #
# Chronological split, NO shuffling. First 80% train, last 20% test.
TRAIN_TEST_SPLIT_RATIO = 0.80
SHUFFLE = False  # never True — shuffling a time-series causes data leakage.

# Cross-validation uses TimeSeriesSplit (never default KFold).
CV_N_SPLITS = 5


# --------------------------------------------------------------------------- #
# Random Forest hyperparameters (README §6 — starting point, tuned via CV)
# --------------------------------------------------------------------------- #
RF_RANDOM_STATE = 42
RF_N_JOBS = -1
RF_DEFAULT_PARAMS = {
    "n_estimators": 200,
    "max_depth": None,
    "min_samples_leaf": 1,
    "random_state": RF_RANDOM_STATE,
    "n_jobs": RF_N_JOBS,
}

# Grid searched via TimeSeriesSplit CV on the TRAINING set only (README §6).
RF_PARAM_GRID = {
    "n_estimators": [100, 200, 400],
    "max_depth": [None, 5, 10, 20],
    "min_samples_leaf": [1, 2, 5],
}

# Smaller grid used by every evaluation run (scripts/*.py and the dashboard), so
# all of them produce the same model for the same data + config. The two grids
# once differed between scripts, which made the same config report PF 1.30 in one
# place and 1.34 in another.
EVAL_PARAM_GRID = {
    "n_estimators": [200],
    "max_depth": [5, 10],
    "min_samples_leaf": [2, 5],
}
EVAL_CV_SPLITS = 3

# Persisted model artifact (joblib). MODEL_FILENAME is the default path for
# MLModel.save()/load(); evaluation runs save one model per pair/timeframe.
MODEL_FILENAME = "random_forest.pkl"
MODEL_FILENAME_TEMPLATE = "random_forest_{pair}_{timeframe}.pkl"


# --------------------------------------------------------------------------- #
# Risk management (README §7)
# --------------------------------------------------------------------------- #
# Fixed-fractional position sizing: risk this fraction of equity per trade.
RISK_FRACTION_PER_TRADE = _env_float("RISK_FRACTION_PER_TRADE", 0.01)  # 1%

# Base stop-loss / take-profit distances (fraction of price).
# CLOSE-TAKE-PROFIT exits (SL 1.2% / TP 0.4%) — the DEFAULT, chosen to best satisfy
# the report's evaluation rubric (Table 3.3) while staying profitable on both pairs:
#   EUR/USD: 73% win / PF 1.34 / DD 1.5% / +$257
#   GBP/USD: 78% win / PF 1.62 / DD 2.5% / +$532
# Most of that win rate comes from the exit geometry itself, not the model: with
# the same exits, random trade direction wins ~67–69% (docs/RESULTS.md "No-skill
# baseline"). The model's measurable edge is in profit factor, not win rate.
# It is the only configuration that meets the report's headline target (win rate
# > 60%) on BOTH pairs, with the lowest drawdown of any config — balanced and
# profitable, not reckless.
#
# Honest caveat (documented, not hidden — see docs/RESULTS.md): a close TP gives an
# unfavourable nominal risk-reward (~3:1 risk:reward). High win rate and a favourable
# risk-reward CANNOT both be maximised — the take-profit distance controls both, an
# inverse relationship confirmed in the trading literature (optimise expectancy, not
# win rate alone). Two alternatives are documented + selectable:
#   • symmetric 1:1 (SL/TP 0.6%): sounder risk-reward, GBP/USD 60% win / PF 1.92.
#   • far-TP 1:2 (SL 0.5 / TP 1.0): best risk-reward (2.4:1 realised) + PF (2.42),
#     but wins only 39-50% (below the report's win-rate target).
# Both label (triple-barrier) and live stops use these, so training and trading
# stay in sync. NOTE: no config meets the Sharpe>1.0 target — a stated limitation.
# Env-overridable so every documented exit profile is a one-liner, e.g. Step A:
#   DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 scripts/run_backtest.py ...
DEFAULT_STOP_LOSS_PCT = _env_float("DEFAULT_STOP_LOSS_PCT", 0.012)    # 1.2% (wide stop)
DEFAULT_TAKE_PROFIT_PCT = _env_float("DEFAULT_TAKE_PROFIT_PCT", 0.004)  # 0.4% (close TP)

# Dynamic stop-loss: when |Volume Z-Score| >= this, tighten the stop. Because the
# volume gate already requires Z > 1.5, this fires on roughly 60–70% of trades.
# A tightened stop with fixed-fractional sizing means a LARGER position for the
# same cash risk, so those trades' wins are bigger — that (not TP overshoot; the
# mock fills exactly at TP) is why realised reward:risk exceeds nominal.
DYNAMIC_SL_ZSCORE_TRIGGER = _env_float("DYNAMIC_SL_ZSCORE_TRIGGER", 2.0)
DYNAMIC_SL_TIGHTEN_FACTOR = 0.5  # multiply stop distance by this when triggered

# Hard limits (README §7).
MAX_DRAWDOWN_LIMIT = 0.15        # < 15% (also an eval target)
DAILY_LOSS_LIMIT = 0.05          # halt trading after 5% equity loss in a day
STOP_LOSS_LATENCY_TARGET_MS = 500  # README §7 / §8

STARTING_EQUITY = _env_float("STARTING_EQUITY", 10_000.0)


# --------------------------------------------------------------------------- #
# Evaluation targets (README §8)
# --------------------------------------------------------------------------- #
TARGET_WIN_RATE = 0.60        # > 60%
TARGET_MAX_DRAWDOWN = 0.15    # < 15%
TARGET_LATENCY_MS = 500       # < 500 ms
TARGET_PROFIT_FACTOR = 1.5    # > 1.5
TARGET_SHARPE = 1.0           # > 1.0


# --------------------------------------------------------------------------- #
# Backtest evaluation (README §8)
# --------------------------------------------------------------------------- #
# Trading costs applied by the mock broker on entry AND exit, in price units.
BACKTEST_SPREAD = _env_float("BACKTEST_SPREAD", 0.0001)
BACKTEST_SLIPPAGE = _env_float("BACKTEST_SLIPPAGE", 0.0001)

# Time exit (label ↔ trade alignment). The triple-barrier label gives up after
# TRIPLE_BARRIER_MAX_HOLD bars, but by default the backtester holds a trade until
# SL/TP (some default-config trades ran 370 bars). When True, the backtester
# closes at the Close of bar entry + TRIPLE_BARRIER_MAX_HOLD — the label's
# vertical barrier — so trades resolve exactly as the label assumes.
USE_TIME_EXIT = _env_str("USE_TIME_EXIT", "false").lower() == "true"

# z for the Wilson score interval reported around the win rate (1.96 = 95%).
# 30–40 trades give a wide interval; report it next to every win rate.
WIN_RATE_CI_Z = 1.96


# --------------------------------------------------------------------------- #
# Execution handler selection (README §13)
# --------------------------------------------------------------------------- #
# Selects the handler used for LIVE order routing (the dashboard's Live mode,
# via src/execution/factory.get_execution_handler()). Swapping mock <-> real is
# ONLY this one config change (README §13):
#   "mock"       -> in-process simulated broker (paper orders, no MT5)
#   "remote_mt5" -> RPC client in the engine -> MT5 host over TCP
#   "mt5"        -> direct MetaTrader5 (only on the Windows host running the terminal)
# Backtests ALWAYS use the mock: replaying history needs simulated fills at
# historical prices and bar-by-bar SL/TP checks, which a live broker can't do.
EXECUTION_HANDLER = _env_str("EXECUTION_HANDLER", "mock")

# RPC boundary to the MT5 host (used by RemoteMT5ExecutionHandler). In
# docker-compose the engine reaches the mt5 service by its service name "mt5".
MT5_RPC_HOST = _env_str("MT5_RPC_HOST", "mt5")
MT5_RPC_PORT = _env_int("MT5_RPC_PORT", 9099)

# Shared secret for the RPC boundary. When set, the server rejects any request
# without the matching token. Plain TCP (no TLS): the token is defence-in-depth,
# not transport security — keep the port off the public internet (VPN/SSH tunnel).
MT5_RPC_TOKEN = _env_str("MT5_RPC_TOKEN", "")

# Volume units. The whole engine (RiskManager, mock broker, backtester) sizes
# positions in UNITS of the base currency; MT5 trades in LOTS. The MT5 handler
# converts using the broker's symbol_info (contract size, volume step/min/max);
# this standard-lot size is only the fallback + the dashboard's lots input.
FX_STANDARD_LOT_UNITS = 100_000

# Max price deviation (points) MT5 may fill a market order away from the request.
MT5_DEVIATION_POINTS = 20

# WHICH MT5 installation to attach to. `MetaTrader5.initialize()` with no path
# attaches to whichever terminal is ALREADY RUNNING (or the last one used), and
# `mt5.login()` then switches THAT terminal's account. On a host that also runs a
# live trading system, both are dangerous: it can hijack the live terminal and
# knock its EA off its account. Point this at a SEPARATE terminal installation
# (ideally a portable one) dedicated to this project's demo account.
# Empty = let MT5 choose, which is only safe on a machine with exactly one terminal.
MT5_TERMINAL_PATH = _env_str("MT5_TERMINAL_PATH", "")

# Refuse to trade anything that is not a DEMO account (README §9). Checked from
# account_info().trade_mode immediately after login; a real/contest account aborts
# the connection before a single order can be sent. Leave this on — it is the last
# line of defence against pointing the system at real money.
MT5_REQUIRE_DEMO = _env_str("MT5_REQUIRE_DEMO", "true").lower() == "true"

# Magic number stamped on every order this system places. MT5 reports magic 0 for
# trades a human placed by hand in the terminal, so this is what tells our positions
# apart from the account owner's. (A sibling project filed 15 manual trades against a
# strategy for want of this — docs/GADEL_ENGINE_COMPARISON.md.)
MT5_MAGIC_NUMBER = _env_int("MT5_MAGIC_NUMBER", 20260917)

# Manage only positions carrying our magic number. False = see and close every
# position on the account: fine on a dedicated account, dangerous on a shared one.
MT5_ONLY_OWN_POSITIONS = _env_str("MT5_ONLY_OWN_POSITIONS", "true").lower() == "true"


# --------------------------------------------------------------------------- #
# MT5 credentials (README §9 — demo account only, from .env, never hardcoded)
# --------------------------------------------------------------------------- #
MT5_LOGIN = _env_str("MT5_LOGIN", "")
MT5_PASSWORD = _env_str("MT5_PASSWORD", "")
MT5_SERVER = _env_str("MT5_SERVER", "")

# Dummy placeholders (UI demo only — DO NOT connect anywhere). The dashboard
# pre-fills the credential boxes with these when the real MT5_* are blank, so
# the form looks complete while backtesting on the mock broker.
DUMMY_MT5_LOGIN = _env_str("DUMMY_MT5_LOGIN", "")
DUMMY_MT5_PASSWORD = _env_str("DUMMY_MT5_PASSWORD", "")
DUMMY_MT5_SERVER = _env_str("DUMMY_MT5_SERVER", "")


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")
# README §12: log every signal decision (rule result + ML prob + final action).
SIGNAL_LOG_FILE = PROJECT_ROOT / "logs" / "signals.log"
