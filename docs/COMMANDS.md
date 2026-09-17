# Commands & Setup Guide

Everything needed to install, run, verify and demonstrate the system — from a fresh
machine to a live broker. Copy-pasteable, with the output you should expect.

For *why* the system behaves as it does, see `docs/HOW_IT_WORKS.md`. For the measured
results, `docs/RESULTS.md`. For viva answers, `docs/DEFENCE_GUIDE.md`.

---

## 1. First-time setup

Requires **Python 3.10+** (this machine runs 3.14) and about 500 MB of disk.

```bash
cd ~/Documents/Projects/BotsProjects/scikit-automated-trading-system

# 1. Create the virtual environment (one time)
python3 -m venv .venv

# 2. Install dependencies (core engine — no MetaTrader5, macOS-safe)
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

# 3. Create your local settings file
cp .env.example .env        # then edit it if you have MT5 demo credentials
```

`.env` is gitignored and must never be committed. Leaving the MT5 fields blank is fine:
everything except live trading works without them.

**Do not install `requirements-mt5.txt` here.** It contains the Windows-only
`MetaTrader5` package and belongs on a Windows host (see §6).

### Verify the install

```bash
.venv/bin/python -m pytest -q
```

Expected: **`218 passed, 2 deselected`**. The two deselected tests hit Yahoo Finance
live; run them deliberately with `.venv/bin/python -m pytest -m network -v`.

### A note on the cached data

`data/EURUSD_1h.parquet` and `data/GBPUSD_1h.parquet` are the exact windows every
documented number was measured on (mid-June 2024 → 12 June 2026). They're already in
the repo. If they were deleted, the next run re-downloads a *newer* window from Yahoo
and **every number will shift** — the results would still be honest, just not the ones
in the docs. There is no 4h cache by design; 4h is rebuilt from 1h each time.

---

## 2. The dashboard

```bash
.venv/bin/python -m streamlit run dashboard/app.py
```

Open **http://localhost:8501**. Stop with `Ctrl+C`.

If it asks for an email on first launch, add `--server.headless=true`.

### Backtest mode (the default tab)

Leave the sidebar at its defaults — pair `EURUSD`, timeframe `1h`, volume threshold
1.5, ML confidence 0.55, risk 1% — and click **Run Backtest**. It loads the cached
data, trains the model on the training split and replays the held-out period. Expect
15–30 seconds.

| | EUR/USD 1h | GBP/USD 1h |
|---|---|---|
| Win Rate | 73.3% | 78.4% |
| Max Drawdown | 1.5% | 2.5% |
| Profit Factor | 1.34 | 1.62 |
| Sharpe | 0.13 | 0.22 |
| Net P&L | +256.57 | +531.82 |
| Targets met | 2/4 | 3/4 |

Below the metrics: the win-rate confidence interval (56%–86% for EUR/USD), the equity
curve, the trade table (30 rows, with entry/exit times and exit reasons) and the
model's feature importances.

These match `docs/RESULTS.md` exactly — the dashboard and the scripts share one tuning
grid. Moving the sliders changes the results; put them back to reproduce the documented
figures. Running a backtest here does **not** overwrite any saved model.

Switching the timeframe to `4h` also works: GBP/USD is profitable there, EUR/USD is not.

### Live mode (works with no broker)

Switch the radio at the top to **Live (paper or MT5 demo)**. With the shipped default
you'll see:

- a caption reading ``Handler: `mock` ``
- a green box: *"Paper mode (EXECUTION_HANDLER=mock): orders fill in the in-process
  simulated broker at the reference price — no MT5 involved."*

Fill in side, volume (in lots), reference price, stop-loss and take-profit, then click
**Send order**:

```
Order result: {'ticket': 1, 'symbol': 'EURUSD', 'side': 'BUY', 'volume': 10000.0,
               'price': 1.1, 'sl': 1.09, 'tp': 1.12, 'status': 'filled', 'latency_ms': 0.0}
```

Note `volume: 10000.0` — you typed 0.1 lots and it was converted to 10,000 units, the
unit the engine sizes in. The paper handler needs the **reference price** (it fills
there); a real MT5 handler ignores it and fills at market.

This is the safe thing to demo: it exercises the entire execution path with no broker,
no MetaTrader and no network.

### Checking it without a browser

Drives the real app and asserts the numbers:

```bash
PYTHONWARNINGS=ignore .venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, ".")
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("dashboard/app.py", default_timeout=600); at.run()
at.sidebar.button[0].click().run()
print("exceptions:", [e.value for e in at.exception])
print([(m.label, m.value) for m in at.metric])
EOF
```

Expect no exceptions and `Win Rate 73.3%`.

### In Docker

```bash
docker compose up engine        # dashboard on :8501
```

The compose file mounts `data/` and `models/`, so the container uses the same cached
window and produces the same numbers.

---

## 3. Command-line runs

### The canonical evaluation

```bash
.venv/bin/python scripts/run_backtest.py EURUSD 1h
.venv/bin/python scripts/run_backtest.py GBPUSD 1h
```

Prints the configuration used, the split sizes, the §8 metrics with a confidence
interval, a trade breakdown by side and exit reason, pass/fail against each target, and
saves the model with its provenance:

```
=== Backtest: EURUSD 1h ===
config: label_method=triple_barrier, stop_loss_pct=0.012, take_profit_pct=0.004, ...
train=9824 test=2456 (2026-01-20 -> 2026-06-12)

--- Results (with spread+slippage) ---
  win_rate        : 0.7333
  profit_factor   : 1.34
  max_drawdown    : 0.0148
  net_pnl         : 256.57
  win-rate CI     : [55.6%, 85.8%] (Wilson, z=1.96, n=30)

--- Trade breakdown ---
  BUY : 19 trades, win 68.4%, net +68.41
  SELL: 11 trades, win 81.8%, net +188.15
  exits: {'take_profit': 22, 'stop_loss': 7, 'end_of_data': 1}

--- vs README §8 targets ---
  [PASS] Win Rate > 60%          [FAIL] Profit Factor > 1.5
  [PASS] Max Drawdown < 15%      [FAIL] Sharpe > 1.0 (per-trade, unannualised)
  Model saved -> models/random_forest_EURUSD_1h.pkl
```

### The honesty checks

```bash
# Is it the model, or just the exit distances? (model vs random direction)
.venv/bin/python scripts/baseline_noskill.py EURUSD 1h

# Win rate vs reward-to-risk across five exit geometries
.venv/bin/python scripts/sweep_winrate.py EURUSD 1h

# Threshold tuning done honestly (tuned on validation, reported once on test)
.venv/bin/python scripts/tune_thresholds.py EURUSD 1h

# What's inside the saved models, including how they were produced
.venv/bin/python scripts/inspect_model.py
```

The baseline prints the line that matters most in a viva:

```
  model (RF direction)   win  73.3% [55.6%, 85.8%]  PF  1.34  net  +256.57  trades 30
  random direction x20    win mean  68.7% (range 58.1%–79.1%)  PF mean 1.04
```

### Changing the strategy without editing code

Every knob is an environment variable:

```bash
# Far-TP profile — lower win rate, but the model beats every random run
DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 \
  .venv/bin/python scripts/run_backtest.py EURUSD 1h

# Symmetric 1:1
DEFAULT_STOP_LOSS_PCT=0.006 DEFAULT_TAKE_PROFIT_PCT=0.006 \
  .venv/bin/python scripts/run_backtest.py EURUSD 1h

# Make the trades match the label exactly (shows the honest downside)
USE_TIME_EXIT=true LABEL_DYNAMIC_SL=true ALLOW_SHORTS=false \
  .venv/bin/python scripts/run_backtest.py EURUSD 1h

# Re-run a rejected experiment, e.g. RSI at the Step A exits
DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 USE_RSI=true \
  .venv/bin/python scripts/run_backtest.py EURUSD 1h

# 4h timeframe
.venv/bin/python scripts/run_backtest.py EURUSD 4h
```

Every row in `docs/RESULTS.md` has its exact command in that file's Reproducibility
table. Note that each `run_backtest.py` run overwrites
`models/random_forest_<PAIR>_<TF>.pkl`, so re-run the plain default last if you want the
saved models to match the headline numbers.

---

## 4. What runs where: mock vs live

**Backtests always use the mock broker, by design.** Replaying history needs fills at
historical prices and bar-by-bar stop/target checks, which no live broker can provide.
Every number in the docs comes from that simulated broker, with spread and slippage
charged on both entry and exit.

`EXECUTION_HANDLER` in `.env` chooses how the dashboard's **Live tab** routes orders:

| Value | Behaviour | Requires |
|---|---|---|
| `mock` *(default)* | Paper orders filled in memory at your reference price | Nothing |
| `remote_mt5` | Sends each order over the network to a Windows host running the terminal | A Windows machine (§6) |
| `mt5` | Talks to MetaTrader directly — only valid *on* that Windows machine | Windows + MetaTrader5 |

Switching is one line in `.env`; no code changes.

---

## 5. Connecting a real (demo) broker

> **Running an actual demo session?** `docs/LIVE_DEMO_RUNBOOK.md` is the step-by-step
> protocol (`scripts/live_session.py`, what to log, how to report it honestly in
> Chapter 4). This section is the one-time machine setup it depends on.

**Status: the live path is built and unit-tested but has never been run against a real
broker.** MetaTrader's Python API cannot start under Wine — proven exhaustively here and
by a sibling project (`docs/WINE_VERDICT.md`) — so it needs real Windows.

Demo accounts only. Never a funded account (README §9).

1. **Get a demo account** from any MT5 broker; note the login, password and server name.
   The server name must match MetaTrader's own list **letter-for-letter, including
   spaces** — a stored trailing space has cost another project days.
2. **On a Windows machine** (a VPS is roughly $10/month), install MetaTrader 5, log in
   once by hand so the account is saved, and enable **Algo Trading** in the toolbar
   (otherwise orders return error `10027`).
3. **Install the engine there** and the MT5 extras:
   ```cmd
   pip install -r requirements.txt
   pip install -r requirements-mt5.txt
   ```
4. **Run the RPC service** on that machine:
   ```cmd
   python -m src.execution.mt5_service
   ```
   It listens on port 9099. Set `MT5_RPC_TOKEN` in `.env` on **both** machines to the
   same secret — without it, anyone who can reach the port can place orders. The link
   is plain TCP, so keep the port on a private network, VPN or SSH tunnel.
5. **Point the engine at it** — in your local `.env`:
   ```
   EXECUTION_HANDLER=remote_mt5
   MT5_RPC_HOST=<windows host or IP>
   MT5_RPC_PORT=9099
   MT5_RPC_TOKEN=<the same secret>
   ```
6. **Check it** — the dashboard's Live tab should show *"Connected to MT5 RPC service…"*
   in green. Send one small manual order and confirm it appears in MetaTrader. The
   result includes `latency_ms`, the signal-to-fill time.

**What the handler already takes care of** (fixed 2026-09-17 after reviewing a sibling
production system that hit each of these live):

- it requests a fill mode the symbol actually advertises, instead of assuming IOC —
  HFMarkets accepts FOK only and rejects IOC with `10030`;
- every MT5 call runs on one pinned thread, because the library binds the terminal to
  whichever thread connected first;
- orders carry a magic number, so our positions are distinguishable from trades you place
  by hand — and closing one of yours is refused (`MT5_ONLY_OWN_POSITIONS`);
- broker rejections come back with a readable reason (e.g. `10027` = AutoTrading is off);
- login and server names are whitespace-stripped, since MT5 matches them exactly.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `streamlit: command not found` | Use `.venv/bin/python -m streamlit`, never bare `streamlit` |
| `ModuleNotFoundError: config` | Run from the project root, or use the `.venv` interpreter |
| Port 8501 already in use | `--server.port 8502` |
| Dashboard numbers ≠ the docs | A slider moved — reset to 1.5 / 0.55 / 1.0% |
| All numbers changed after a re-fetch | The cached parquet was replaced with a newer window |
| Warning about "nonzero volume" | The volume data is stale or the futures merge failed — re-fetch with `force_refresh=True` |
| 4h produces no trades | Was the old stale-cache bug; 4h is now rebuilt from 1h automatically |
| Live tab shows a warning, not green | `EXECUTION_HANDLER` isn't `mock`, or the Windows host is unreachable |
| Every live call says `unauthorized` | `MT5_RPC_TOKEN` differs between the two machines |
| Live order rejected `below_min_volume` | The computed size is under the broker's minimum lot — by design, we reject rather than round up |
| `Refusing to trade: account … is NOT a demo account` | Working as intended — that login is a live account. Use a demo one. `MT5_REQUIRE_DEMO=false` exists but means real money |
| `account_info() returned nothing … cannot be verified` | The terminal isn't logged in, or `initialize()` attached to a terminal you didn't expect — set `MT5_TERMINAL_PATH` |
| It connected to the **wrong terminal** | `initialize()` with no path grabs whichever terminal is already running. Set `MT5_TERMINAL_PATH` to your own installation's `terminal64.exe` |
| `scripts/make_progress_docx.py` fails | Needs `pip install python-docx` (not a core dependency) |

---

## 7. Quick reference

```bash
.venv/bin/python -m pytest -q                            # 218 tests
.venv/bin/python -m pytest -m network -v                 # live Yahoo smoke tests
.venv/bin/python scripts/run_backtest.py EURUSD 1h       # headline result
.venv/bin/python scripts/baseline_noskill.py EURUSD 1h   # is it the model?
.venv/bin/python scripts/sweep_winrate.py EURUSD 1h      # exit-geometry frontier
.venv/bin/python scripts/tune_thresholds.py EURUSD 1h    # validation-tuned thresholds
.venv/bin/python scripts/inspect_model.py                # saved models + provenance
.venv/bin/python -m streamlit run dashboard/app.py       # dashboard on :8501
docker compose up engine                                 # containerised dashboard
```
