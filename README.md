# Automated Financial Trading System

A transparent, self-hosted automated Forex trading system that combines **statistical Z-Score filtering** with a **Random Forest machine learning classifier** to generate and execute trades. Built for retail traders on standard consumer hardware — no GPU, no expensive cloud subscriptions, no black-box models.

> **Academic context:** B.Sc. Computer Science final-year project —  *Design and Implementation of an Automated Financial Trading System* . This README is the canonical build spec; the chapter report is the academic write-up. Where they ever disagree,  **this README wins for implementation** .

---

## 1. Core Design Decision (read this first)

**The predictive engine is a Random Forest classifier from Scikit-Learn. There is NO deep learning in this project.**

* ✅ Use: `scikit-learn` (Random Forest), `pandas`, `numpy`
* ❌ Do NOT use, import, or add to `requirements.txt`: `tensorflow`, `keras`, `torch`, any LSTM/neural-network code

**Why Random Forest over deep learning (e.g. LSTM):**

1. Runs efficiently on standard consumer CPUs — matches the retail-accessibility and low-latency goals.
2. Ensemble averaging across many decision trees inherently resists overfitting.
3. Interpretable (feature importances) — supports the transparency goal. LSTM is a black box.
4. Keeps the Docker image lightweight (TensorFlow is hundreds of MB plus CUDA complexity).

LSTM/deep learning is discussed in the academic report  **only as a reviewed-and-rejected alternative** . Do not implement it.

---

## 2. System Architecture

A modular, decoupled design. The heavy analytical processing (Python) is fully separated from trade execution (MetaTrader 5).

```
┌─────────────────┐     ┌──────────────────────────────────────┐     ┌──────────────┐
│  Yahoo Finance  │────▶│         Python Analytical Engine        │────▶│ MetaTrader 5 │
│   (yfinance)    │     │                                          │     │   (broker)   │
└─────────────────┘     │  DataHandler → Preprocessor → MLModel    │     └──────────────┘
                        │       → SignalGenerator (hybrid logic)   │
                        └──────────────────────────────────────────┘
                                          │
                                          ▼
                                ┌───────────────────┐
                                │ Streamlit Dashboard│
                                │  (monitor/control) │
                                └───────────────────┘
              All containerised with Docker for 24/7 deployment
```

### The hybrid signal logic (the heart of the system)

A trade is generated  **only when BOTH conditions agree** :

1. **Rule-based filter:** Z-Score of current trading **Volume > +1.5** (confirms institutional participation / abnormal activity).
2. **ML confirmation:** Random Forest outputs a directional probability above the configured confidence threshold (bullish class 1 vs. bearish/neutral class 0).

If either fails → hold (no trade). This suppresses false signals during noisy, sideways markets while keeping ML adaptability.

---

## 3. Tech Stack

| Layer            | Technology                                 | Purpose                                                               |
| ---------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| Language         | **Python 3.10+**                     | Core analytical engine                                                |
| Data acquisition | **yfinance**                         | Fetch historical + real-time OHLCV                                    |
| Data processing  | **pandas, numpy**                    | Cleaning, Z-Score computation                                         |
| Machine learning | **scikit-learn**                     | Random Forest classifier, train/test split, cross-validation, metrics |
| Execution        | **MetaTrader5**(official Python lib) | Route Buy/Sell orders, demo account                                   |
| Visualisation    | **matplotlib**                       | Performance charts                                                    |
| UI / Dashboard   | **streamlit**                        | Web-based control & monitoring                                        |
| Deployment       | **Docker**                           | Containerised 24/7 operation                                          |

**Why these (vs. alternatives):**

* **Python over MQL5:** MQL5 lacks robust ML libraries.
* **MT5 over MT4:** MT5 has a native, officially supported Python API; MT4 needs unstable third-party DLL bridges.
* **Streamlit over React:** Rapid data-script-to-dashboard; no need for a heavy full-stack frontend for a local tool.

---

## 4. Suggested Project Structure

```
automated-trading-system/
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── config/
│   └── settings.py            # thresholds, pairs, timeframes, risk params
├── src/
│   ├── __init__.py
│   ├── data_handler.py        # DataHandler — yfinance connection & fetch
│   ├── preprocessor.py        # Preprocessor — cleaning + Z-Score features
│   ├── ml_model.py            # MLModel — Random Forest train/predict/persist
│   ├── signal_generator.py    # Hybrid rule + ML decision logic
│   ├── risk_manager.py        # Position sizing, stop-loss, drawdown limits
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── base.py            # ExecutionHandler — abstract interface
│   │   ├── mock.py            # MockExecutionHandler — for dev/backtest on macOS
│   │   └── mt5.py             # MT5ExecutionHandler — real, runs in Wine/Docker
│   └── backtester.py          # Historical evaluation engine
├── docker/
│   └── mt5/                   # Wine + headless MT5 container (see §13)
│       └── Dockerfile
├── dashboard/
│   └── app.py                 # Streamlit interface
├── models/                    # Saved .pkl model artifacts (gitignored)
├── data/                      # Cached datasets (gitignored)
├── notebooks/                 # Optional exploration
└── tests/
    └── test_*.py
```

---

## 5. Data Specification

* **Source:** Yahoo Finance via `yfinance`.
* **Pairs:** EUR/USD and GBP/USD (high liquidity).
* **History:** 5 years, 2019–2024.
* **Timeframes:** 1-hour and 4-hour candles.
* **Raw fields:** Open, High, Low, Close, Volume (OHLCV).

### Z-Score normalisation

Standardise features so the model isn't distorted by raw price scale:

```
Z = (x − μ) / σ
```

where `x` = feature value (e.g. Close or Volume), `μ` = rolling historical mean, `σ` = rolling standard deviation. Use a  **rolling window** , not a global mean, to capture relative market positioning over time.

### Model input features

* Open, High, Low, Close (per candle)
* Volume
* Z-Score of Close (rolling)
* Z-Score of Volume (rolling)

### Model output

A directional probability score (likelihood of bullish continuation). The hybrid layer uses it to trigger / hold / suppress a trade.

### Train/test split — CRITICAL

* **Chronological** split, no shuffling. Financial time-series must preserve temporal order.
* First **80%** (≈2019 → mid-2023) = training set.
* Last **20%** (≈mid-2023 → 2024) = hold-out test set.
* **Never shuffle or randomise** — doing so causes data leakage (training on the future). Use `sklearn.model_selection.TimeSeriesSplit` for cross-validation, not the default `KFold`.

---

## 6. Machine Learning Details

* **Classifier:** `sklearn.ensemble.RandomForestClassifier`
* **Task:** Supervised binary classification — class 1 = bullish continuation, class 0 = bearish/neutral.
* **Not** regression (no continuous price prediction) and **not** reinforcement learning.

**Overfitting mitigation (all required):**

1. Random Forest ensemble averaging (built-in).
2. Hyperparameter tuning via **cross-validation on the training set only** — tune `max_depth`, `min_samples_leaf`, `n_estimators`. Use `TimeSeriesSplit`.
3. Z-Score normalisation reduces sensitivity to outliers.
4. Final evaluation on the strictly held-out 2024 test set only.

```python
from sklearn.ensemble import RandomForestClassifier
# example starting point — tune via CV, do not hardcode blindly
model = RandomForestClassifier(
    n_estimators=200,
    max_depth=None,        # tune
    min_samples_leaf=1,    # tune
    random_state=42,
    n_jobs=-1,
)
```

---

## 7. Risk Management

* **Position sizing:** fixed-fractional (volume as a % of total equity), not fixed lot size — reduces catastrophic drawdown risk.
* **Dynamic stop-loss:** when abnormal volatility is detected (large Z-Score deviation), tighten stop-loss parameters. Static stops fail during high-impact news.
* **Stop-loss latency target:** execute within **500 ms** of trigger.
* **Hard limits:** enforce a daily loss limit and a maximum drawdown ceiling (< 15%).

---

## 8. Evaluation Targets

| Metric            | Calculation                             | Target   |
| ----------------- | --------------------------------------- | -------- |
| Win Rate          | Profitable trades / total trades × 100 | > 60%    |
| Maximum Drawdown  | Peak-to-trough equity decline           | < 15%    |
| Execution Latency | Signal → MT5 fill                      | < 500 ms |
| Profit Factor     | Gross profit / gross loss               | > 1.5    |
| Sharpe Ratio      | Risk-adjusted return                    | > 1.0    |

### Test scenarios to validate against

* **Ranging market (low volatility):** identify low Z-Scores → withhold trades. Expect zero trades in the ranging window.
* **Trending market (high volatility):** identify high-volume points of interest → execute with the trend.
* **News spike (extreme sudden move):** detect abnormal standard deviations → instantly tighten stop-loss.

---

## 9. Safety Rules (non-negotiable)

* **Demo account ONLY** for all testing and evaluation. Never connect a live-funded account during development.
* **Never commit credentials.** MT5 Login ID, Password, and Server go in `.env` (gitignored). Provide `.env.example` with blank placeholders.
* Credentials are entered by the user through the Streamlit UI or `.env` — never hardcoded.
* Scope is  **fiat Forex only** . No fundamental analysis / news NLP. No High-Frequency Trading (retail latency can't support it).

---

## 10. Implementation Workflow (build order)

1. **DataHandler** — connect to Yahoo Finance, fetch & cache OHLCV for EUR/USD & GBP/USD (1h, 4h).
2. **Preprocessor** — clean data, compute rolling Z-Scores for Close & Volume, assemble feature set, chronological 80/20 split.
3. **MLModel** — train Random Forest, tune via `TimeSeriesSplit` CV, persist model to `models/`, expose `predict_proba`.
4. **SignalGenerator** — implement hybrid logic (Volume Z-Score > +1.5 AND ML probability > threshold).
5. **RiskManager** — position sizing, dynamic stop-loss, drawdown/daily-loss limits.
6. **ExecutionHandler interface + MockExecutionHandler** — define the abstract execution interface (see §13) and a mock implementation so the engine and backtester run with no MT5 dependency.
7. **Backtester** — run on the held-out test set against the mock handler, produce the metrics in §8.
8. **MT5ExecutionHandler** — the real implementation of the interface: connect to MT5 demo (headless under Wine in Docker, see §13), route orders, confirm fills.
9. **Streamlit dashboard** — credential input, parameter controls (lot size, risk tolerance), live positions, performance charts.
10. **Dockerise** — `Dockerfile` + `docker-compose.yml` for 24/7 deployment.

---

## 11. requirements.txt (exact — no TensorFlow)

```
python>=3.10
yfinance
pandas
numpy
scikit-learn
MetaTrader5
matplotlib
streamlit
joblib
python-dotenv
```

> If you ever see `tensorflow` or `keras` appear in `requirements.txt`, the code, or an import — that's a bug. Remove it. The report's tech-stack section was corrected to drop TensorFlow; keep code, requirements, and report telling the same Random-Forest-only story.

> **`MetaTrader5` is Windows-only.** It will not install on macOS/Linux. Keep it in a *separate* requirements file (e.g. `requirements-mt5.txt`) installed only inside the Wine/Docker execution container — see §13. The core engine's `requirements.txt` must remain installable on macOS without it.

---

## 12. Notes for the coding agent

* Keep modules decoupled — analytical engine must not depend on MT5 being connected (so backtesting works offline).
* Write small, testable functions; add `tests/` as you build each module.
* Use `joblib` to save/load the trained model.
* Log every signal decision (rule result + ML probability + final action) for transparency and viva defence.
* Default config values live in `config/settings.py` — never scatter magic numbers (the +1.5 threshold, 80/20 split, 60% target) across the codebase.

---

## 13. Platform Notes: macOS Dev + Headless MT5 (Wine in Docker)

**The problem:** Development happens on macOS, but the official `MetaTrader5` Python package is  **Windows-only** . MT5 itself is a GUI Windows application. We need it running for live/demo execution, but with **minimal RAM/CPU** — i.e. headless.

### Strategy: depend on an interface, not on MT5

All trade execution goes through an abstract interface so nothing in the analytical engine ever imports `MetaTrader5` directly.

```python
# src/execution/base.py
from abc import ABC, abstractmethod

class ExecutionHandler(ABC):
    @abstractmethod
    def connect(self) -> bool: ...
    @abstractmethod
    def place_order(self, symbol: str, side: str, volume: float,
                    sl: float, tp: float) -> dict: ...
    @abstractmethod
    def get_open_positions(self) -> list: ...
    @abstractmethod
    def close_position(self, ticket: int) -> dict: ...
    @abstractmethod
    def disconnect(self) -> None: ...
```

* **`MockExecutionHandler`** — pure-Python simulation. Used for all development, unit tests, and backtesting on macOS. No MT5, no Wine, no Docker needed.
* **`MT5ExecutionHandler`** — the real implementation, imports `MetaTrader5`, runs only inside the Wine/Docker container.

The engine, signal generator, risk manager, and backtester depend on `ExecutionHandler` only. Swapping mock ↔ real changes one line of config, nothing else.

### Headless MT5 under Wine in Docker

MT5 is a GUI app, so "headless" means running it under a **virtual framebuffer** (no real display) rather than a true no-GUI mode — the terminal must still initialise for the Python API to attach.

Approach:

* Base image: a Wine-on-Linux image (e.g. a `tobix/pywine`-style image or a custom Debian + Wine build) with **Python installed inside the Wine prefix** so the Windows `MetaTrader5` package can run.
* Run the MT5 terminal under **`xvfb`** (X virtual framebuffer) to satisfy its GUI requirement with no real display and minimal memory.
* Start MT5 in **portable mode** and disable non-essential terminal features to keep the footprint small.
* The Python execution code runs inside the same Wine prefix and talks to the local terminal via the `MetaTrader5` API.
* Expose the execution layer to the (Linux-side) analytical engine over a thin RPC/socket boundary, OR run the whole execution service in the container and have it subscribe to signals — keep this boundary clean and documented.

### Resource-minimisation requirements

* No MT5 GUI rendered to a real display — `xvfb` only.
* Strip the Wine prefix to essentials; don't bundle unused Windows components.
* Run a single MT5 terminal instance; don't spawn duplicates.
* Set container memory limits in `docker-compose.yml` and verify the headless terminal stays within them.

### Separate dependency files

* `requirements.txt` — core engine, macOS-installable,  **no `MetaTrader5`** .
* `requirements-mt5.txt` — `MetaTrader5` and any Windows-side deps, installed  **only inside the Wine container** .

### Build/test implication

Everything except the real broker connection can be built, run, and backtested on macOS against `MockExecutionHandler`. The Wine/Docker/headless-MT5 work is isolated to the `MT5ExecutionHandler` and its container — tackle it last (build step 8), after the engine is proven end-to-end with the mock.
