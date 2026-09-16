# How It Works — A Plain-English Guide to Each Module

This doc explains every part of the system in simple terms, so you can follow
along, learn, and defend it in your viva. Read it top to bottom — each module
feeds the next.

> **Mental model:** the system is an assembly line. Raw market data goes in one
> end, and a Buy/Sell/Hold decision comes out the other. Each module is one
> station on the line that does exactly one job and hands its output to the next.

```
Yahoo Finance → DataHandler → Preprocessor → MLModel → SignalGenerator → RiskManager → ExecutionHandler
   (raw data)    (fetch+clean) (features+labels) (predict)  (decide)        (size+stops)   (place order)
```

---

## The big idea (read this first)

We are **not** trying to predict the exact future price. For each hour we ask a
yes/no question that matches how a trade actually ends: **"If I bought here, would
the take-profit be hit before the stop-loss (within the next 24 hours)?"** That is a
*classification* problem (two buckets: "yes" = 1, "no" = 0), which is why we use a
**Random Forest classifier**. (The very first version asked the simpler "will the
next candle close higher?" — it lost money; switching the question was the single
biggest improvement. See `docs/TRIPLE_BARRIER_EXPLAINED.md`.)

But a model alone is risky on noisy market data, so we add a **rule** on top: only
trade when **trading volume is abnormally high** (a sign that big players are
active). A trade fires **only when the rule AND the model agree**. This is the
"hybrid" in the project title. Either one says no → we **hold** (do nothing).

---

## What is a Z-Score? (you need this everywhere)

A Z-Score answers: *"How unusual is this number compared to what's normal lately?"*

```
Z = (value − recent average) / recent standard deviation
```

- **Z = 0** → exactly average.
- **Z = +2** → way above average (2 standard deviations up).
- **Z = −1.5** → well below average.

We use a **rolling** (moving) window — the last 20 candles — so "normal" keeps up
with the market instead of being frozen. The rule "Volume Z-Score > +1.5" just
means *"volume right now is unusually high versus the recent norm."*

---

## Module 1 — DataHandler (`src/data_handler.py`)

**Job:** Get clean price data from Yahoo Finance and cache it.

**In simple terms:** This is the "go fetch the ingredients" station. It downloads
the Open/High/Low/Close/Volume (OHLCV) candles for EUR/USD and GBP/USD, tidies
them up, and saves a copy to `data/` so we don't re-download every time.

**What it actually does:**
- Connects to Yahoo Finance via the `yfinance` library.
- Fetches **1-hour** candles and caches them (`data/EURUSD_1h.parquet`, …).
- Builds **4-hour** candles by grouping four 1-hour candles together (Yahoo doesn't
  offer 4h directly). The 4h series is rebuilt from the cached 1h data every time
  it's asked for and is **never cached on its own**, so it can't fall out of step
  with the 1h data. (It once did: an old 4h cache from before the volume fix had
  zero volume, which silently produced zero 4h trades.)
- **Cleans** the data: sorts by time, removes duplicate timestamps, fills tiny gaps,
  and converts every timestamp to **UTC** (Yahoo sends spot FX in London time).
- **Checks the data:** if fewer than half the candles have any volume, it logs a
  warning — the volume rule can't work on a zero-volume series.

**One real-world limitation you must know (and can defend):** Yahoo only gives
*hourly* data for about the **last 730 days** (~2 years), not the full 2019–2024.
So we fetch the deepest window it allows and **log the actual dates we got**. The
cached data runs mid-June 2024 → 12 June 2026: ~12,300 hourly candles per pair,
plenty to train on. The held-out test period is therefore **20 Jan → 12 Jun 2026**,
not "2024" as the report's Chapter 3 assumed.

**Key terms:**
- **OHLCV** = Open, High, Low, Close, Volume — the five numbers describing one candle.
- **Candle / timeframe** = one time-bucket of price (e.g. one hour).
- **Resampling** = combining small candles into bigger ones (1h → 4h).

---

## Module 2 — Preprocessor (`src/preprocessor.py`)

**Job:** Turn clean candles into the exact numbers the model learns from, plus the
"right answers" to learn against, then split into train/test.

**In simple terms:** The "prep the ingredients" station. The model can't eat raw
candles as-is — it needs **features** (clues) and **labels** (the answer key).

**What it produces:**
1. **Features** (the clues the model sees): Open, High, Low, Close, Volume, plus the
   **Z-Score of Close** and **Z-Score of Volume**.
2. **Label** (`Target`), the **triple-barrier** label: for each candle, imagine
   buying at its close with a take-profit and a stop-loss (the same distances the
   RiskManager uses). Walk forward up to 24 candles: take-profit touched first → `1`;
   stop-loss touched first → `0`; neither → `1` if price ended higher, else `0`.

**Two directions you must keep straight — this is the #1 way people cheat by accident:**
- **Features look BACKWARD.** The Z-Score at 3pm uses only data up to 3pm. It never
  peeks at 4pm. (We tested this: deleting future rows doesn't change a past Z-Score.)
- **The label looks FORWARD** (it's literally "what happens next") — but the label is
  the *answer*, never fed back in as a clue. The model must *guess* it.

If a feature accidentally contained future info, the model would look brilliant in
testing and fail with real money. This mistake is called **data leakage**, and
avoiding it is the whole reason for the rules below.

**The train/test split (critical):**
- We use the **first 80% of time** to train and the **last 20%** to test.
- We **never shuffle.** With time-series, shuffling lets the model "study tomorrow's
  answers before today's exam" — that's leakage. So every training candle comes
  *before* every test candle, just like real life.

**Key terms:**
- **Feature** = an input clue for the model.
- **Label / Target** = the correct answer the model tries to predict.
- **Train set** = data the model learns from. **Test set** = unseen data we grade it on.
- **Data leakage** = accidentally letting future info into training; makes results fake.

---

## Module 3 — MLModel (`src/ml_model.py`)

**Job:** Learn the patterns, then output a **probability** that a buy here would
hit its take-profit first.

**In simple terms:** The "brain." It studies thousands of past candles and learns
which combinations of features tend to come before a winning setup.

**What is a Random Forest?** Imagine asking **200 different decision-tree "experts"**
the same yes/no question, where each expert looks at the data slightly differently.
Then you take a **vote**. One expert can be wrong or over-confident, but the crowd
average is steady and hard to fool. That averaging is why a forest **resists
overfitting** (memorising noise instead of learning real patterns).

**Why Random Forest and not deep learning (LSTM/neural nets)?**
- Runs fast on a normal laptop CPU — no expensive GPU.
- Resists overfitting automatically (the voting).
- **Transparent**: it can tell you *which features mattered* (feature importances).
  A neural net is a black box. Transparency is a core goal of this project.

**What it outputs:** not just "yes" or "no", but a **probability** like `0.63`,
meaning "63% confident this is a winning setup." The signal step needs this number,
not a yes/no, so it can apply a confidence threshold.

**How we tune it honestly (TimeSeriesSplit):** A model has settings (how many trees,
how deep, etc.). To pick the best settings we test combinations using
**cross-validation** — but a *time-aware* kind called **`TimeSeriesSplit`**. Normal
cross-validation (`KFold`) shuffles data, which would leak the future again. We
**never** use `KFold` here. And all tuning happens on the **training set only** —
the test set stays sealed until the final grade, so the score is trustworthy. Every
evaluation script and the dashboard use the same small tuning grid
(`EVAL_PARAM_GRID`), so they all produce the same model and the same numbers.

**Saving the brain:** each evaluation run saves the trained model to
`models/random_forest_<PAIR>_<TIMEFRAME>.pkl` with `joblib`, **together with where it
came from** — pair, data window, label and exit settings, date trained — so a file on
disk always says what produced it.

**About the `.pkl` file (the saved model):**
- **What it is:** the trained Random Forest (plus that provenance) saved as a
  `.pkl` ("pickle") — Python's way of writing an in-memory object to disk as **binary**.
- **How it's made:** *not* compiled. At runtime, `joblib.dump(...)` takes the trained
  model from RAM and writes its bytes to disk. `joblib.load(path)` reverses it.
- **Why you can't open it in a "PKL viewer" extension:** joblib uses pickle protocol 5
  with raw numpy arrays inside; most viewer extensions can't parse that and throw a
  "stack not empty" error. The file is fine — the viewer just can't read it.
- **How to view it instead:** `.venv/bin/python scripts/inspect_model.py` prints the
  settings, the provenance and the feature importances of every model in `models/`.

**An honest result you should understand:** the model's edge is thin. Short-term FX
is close to random, and a model that claimed 90% accuracy would almost certainly be
cheating via leakage. In fact, most of the default configuration's 73–78% win rate
comes from the *exit geometry*, not the model: with the same exits, picking the trade
direction at random already wins ~67–69%. The model's real contribution shows up in
**profit factor** (1.34 / 1.62 vs ~1.04 for random) — and, much more clearly, in the
far-take-profit configuration, where it beats every random run (docs/RESULTS.md
"No-skill baseline").

> **Volume data — solved (important for your report):** Yahoo reports **volume = 0**
> for *spot* Forex (`EURUSD=X`) because spot FX is decentralised — there's no central
> exchange to count volume. So we take **price from spot** (the real EUR/USD rate the
> report studies) and **volume from the matching CME FX *futures*** (`6E=F` for EUR,
> `6B=F` for GBP) — a central exchange that *does* report real volume — aligning the
> two by timestamp. CME FX-futures volume is the standard proxy for *institutional*
> FX activity, which is exactly what the report's volume gate is meant to detect
> (§3.3.1, "institutional participation"). After this fix, volume is nonzero on ~88%
> of 1h candles and the +1.5 gate fires on ~13% of them — a real, selective filter.
> Controlled by `USE_FUTURES_VOLUME` and the `VOLUME_SOURCE` map in
> `config/settings.py`; if the futures fetch ever fails it falls back to spot volume
> and logs it (and the data check above then warns).

**Key terms:**
- **Classifier** = a model that sorts things into buckets (here: win vs not-win).
- **Random Forest** = many decision trees voting together.
- **predict_proba** = the model's confidence as a probability (0 to 1).
- **Overfitting** = memorising noise; looks great in training, fails in reality.
- **Cross-validation** = testing settings on slices of the training data.
- **TimeSeriesSplit** = cross-validation that respects time order (no shuffling).
- **Hyperparameters** = the model's settings we tune (tree count, depth, etc.).

---

## Module 4 — SignalGenerator (`src/signal_generator.py`)

**Job:** Make the final call — **Buy, Sell, or Hold** — for each candle.

**In simple terms:** The "decision maker." It takes two inputs and applies one
strict rule: **trade only if BOTH agree.** This is the "hybrid" idea in action.

**The two gates (both must pass):**
1. **Volume gate:** is Volume Z-Score **above +1.5**? (Are big players active?)
2. **ML gate:** is the model **confident**? (P(win) above the 0.55 threshold for a
   BUY, or clearly below it — under 0.45 — for a SELL.)

**The logic (a truth table):**

| Volume gate | ML gate | Result |
|-------------|---------|--------|
| pass | confident UP | **BUY** |
| pass | confident DOWN | **SELL** (unless long-only) |
| pass | unsure | **HOLD** |
| fail | anything | **HOLD** |

So **either gate failing = HOLD** (do nothing). This is the whole point: it makes
the system *trade less but trade better* — it stays out of noisy, low-conviction
moments. Direction (Buy vs Sell) comes from the probability: high = up = Buy.

**About the SELL side (know this for the viva):** the README states the ML gate on
the *bullish* class only, and the label only describes *buy* trades. Selling when
the model is confident a buy would fail is this implementation's extension. It is
partly justified — "the stop was hit first" means price fell far enough that a
mirrored short would have won — but a "no" from a time-out implies nothing. Setting
`ALLOW_SHORTS=false` makes the system long-only; measured, that loses money on the
default config (docs/RESULTS.md "Label/trade alignment").

**Strict "greater than":** exactly 1.5 volume or exactly 0.55 probability does
**not** pass — it must clearly exceed. This avoids acting on borderline cases.

**Transparency:** every decision is recorded with *why* — the probability, the
volume Z-Score, and whether each gate passed. Good for debugging and for showing
the examiner the system's reasoning, not just its output. (It goes to the Python
logger; nothing writes it to a file yet — a known gap.)

**Key terms:**
- **Gate** = a condition that must be true to proceed.
- **Hybrid logic** = combining a fixed rule (volume) with a learned model (ML).
- **Hold** = the safe default; when in doubt, don't trade.

---

## Module 5 — RiskManager (`src/risk_manager.py`)

**Job:** Decide *how much* to trade, *where* to put the stop, and *when to stop
trading* — so one bad run can't wipe the account.

**In simple terms:** The "safety officer." The signal layer says *what* to do;
this layer keeps it survivable. It does three things:

**1. Position sizing (fixed-fractional).** Risk a fixed **percentage of your
current money** each trade (1%), not a fixed lot size. So if you have $10,000
you risk $100; if you drop to $5,000 you only risk $50. Losses automatically make
you bet smaller — that's what stops a losing streak from snowballing. Sizes are in
**units** of currency (e.g. 7,576 euros); the live MT5 handler converts units to
broker **lots** (7,576 units ≈ 0.07 lot).

**2. Dynamic stop-loss.** A stop-loss auto-closes a losing trade at a set price.
Normally it sits a fixed % away. But when volume is extremely unusual
(|Volume Z| ≥ 2), the stop **tightens** to half the distance so a violent move
costs less. Because the volume gate already requires Z > 1.5, this applies to about
half of all trades. And because sizing keeps the cash at risk fixed, a tighter stop
means a *bigger* position — so those trades' wins are about twice as large. (That,
not "overshooting the target", is why the realised win/loss ratio is better than the
nominal one.)

**3. Hard limits (the circuit breakers).** Two automatic "stop everything" rules:
- **Max drawdown** — if the account falls 15% below its highest-ever value, halt.
- **Daily loss** — if you lose 5% in one day, halt for the day.

These cap the worst case no matter what the model or signals say.

**Why this matters most:** remember the edge is thin. A thin edge only makes money if
losses are controlled. Good risk management is what turns "slightly better than a
coin flip" into something survivable.

**Key terms:**
- **Stop-loss** = price level that auto-closes a losing trade.
- **Take-profit** = price level that auto-closes a winning trade.
- **Position size / volume** = how much you trade (units here; lots at the broker).
- **Fixed-fractional** = always risk the same % of current equity.
- **Drawdown** = how far you've fallen from your peak (in %).

---

## Module 6 — ExecutionHandler + MockExecutionHandler (`src/execution/`)

**Job:** Actually place/close orders — through a swappable "plug."

**In simple terms:** This is the part that talks to the broker. The clever bit is
**we don't talk to the broker directly.** We define an **interface** (a contract:
"any broker must have connect, place_order, get_positions, close, disconnect"),
and the rest of the system only ever speaks to that contract.

**Why an interface?** Two reasons:
1. **You develop on a Mac**, where the real MT5 library won't install. The interface
   lets you build and test *everything* against a fake broker first.
2. **Swapping fake ↔ real is one setting** — `EXECUTION_HANDLER` in `.env`. No other
   code changes.

**Three implementations of the same contract:**
- **MockExecutionHandler** — a pretend broker in pure Python. It "fills" orders,
  remembers your open positions, closes them, and works out profit/loss — all in
  memory. It models **spread and slippage** (the real costs) and checks each bar for
  stop-loss / take-profit hits. The backtester always runs against it.
- **MT5ExecutionHandler** — the *real* broker connection. Same five methods, but it
  talks to MetaTrader 5, and converts the engine's units into the broker's lots
  (rounding down, so it never risks more than planned). It runs only on Windows.
- **RemoteMT5ExecutionHandler** — a "phone line" to the Windows machine: it forwards
  every call over the network to the real handler running there.

**What `EXECUTION_HANDLER` controls:** the dashboard's Live mode. `mock` = paper
orders to the pretend broker; `remote_mt5` = real demo orders via the Windows
machine; `mt5` = direct, only when running on that Windows machine itself.
Backtests *always* use the mock — replaying history needs fills at historical
prices, which a live broker can't give.

**Key terms:**
- **Interface / abstract class** = a contract of methods, no implementation.
- **Mock** = a fake stand-in used for testing.
- **Spread / slippage** = real trading costs the mock simulates.
- **Ticket** = a unique ID for each open position.
- **Lot** = the broker's unit of size (1 standard lot = 100,000 units).

---

## Module 7 — Backtester (`src/backtester.py`)

**Job:** Replay history through the *whole* system and measure if it makes money.

**In simple terms:** A "time machine" for the strategy. It feeds the held-out test
candles (data the model never trained on) through the full line — signal → risk →
mock broker — one candle at a time, and tallies the results. This is the honest
answer to *"does it work?"*

**How one candle is processed:**
1. Check open trades — did this candle's High/Low hit a stop-loss or take-profit?
   (Optionally, `USE_TIME_EXIT=true` also closes a trade after 24 candles, exactly
   like the label's time limit.)
2. If risk limits allow and no trade is open, ask the SignalGenerator for a decision.
3. If BUY/SELL, the RiskManager sizes it and the mock broker "fills" it.
At the end, close any trade still open and compute the scorecard. Every trade records
when it opened and closed, how many candles it lasted, and why it closed.

**The scorecard (README §8 metrics):**
- **Win Rate** — % of trades that made money, **with a 95% confidence range**. With
  only ~30 trades that range is wide (e.g. 73% really means "somewhere between 56%
  and 86%"), so always quote both.
- **Max Drawdown** — worst peak-to-trough drop (risk).
- **Profit Factor** — gross profit ÷ gross loss (>1 = profitable).
- **Sharpe Ratio** — return adjusted for how bumpy it was. Ours is measured *per
  trade*, not per year, so it isn't directly comparable to the report's > 1.0 target.

**Costs are included.** The mock broker applies spread + slippage, so the numbers
reflect *real* trading, not a fantasy where fills are free.

**The honesty checks:** the scorecard alone can mislead, so the project also runs a
**no-skill baseline** (same exits, random trade direction — `scripts/baseline_noskill.py`)
to show how much is the model and how much is the exit geometry, and measures what
happens when the trades are made to match the label exactly (docs/RESULTS.md).

**What the first run showed (and why it was fine):** before the triple-barrier label,
the strategy lost money (win rate ~20–26%) but max drawdown **passed** — risk
management worked. A suspiciously *profitable* first result would more likely have
meant a bug than a breakthrough. The improvement phase (docs/RESULTS.md) is the
measured story from there.

**Key terms:**
- **Backtest** = testing a strategy on past data.
- **Held-out / out-of-sample** = data the model never saw in training.
- **Equity curve** = your account balance over time.
- **Confidence interval** = the range the true win rate plausibly lies in.

---

## Module 8 — Real MT5 (`src/execution/mt5.py`, `mt5_service.py`, `docker/mt5/`)

**Job:** The *real* broker connection — the only part that touches a live MT5
terminal. Built last, on purpose, so it never blocks the rest.

**The problem (why this is the hard part):** The official `MetaTrader5` Python
package is **Windows-only** — it will not install on your Mac. And MT5 itself is a
*graphical* Windows app.

**What was tried, and the verdict:** the plan was to run MT5 under **Wine** (runs
Windows programs on Linux) inside Docker, with **xvfb** (a fake invisible screen).
Everything worked up to the broker connection — then `mt5.initialize()` failed. A
sibling project proved this is a hard wall: under Wine the terminal's internal
communication channel never starts (error `-10005`), even on real x86 machines,
while native Windows worked first try with a real demo trade. **Wine is a documented
dead end** (`docs/WINE_VERDICT.md`). The real deployment is a **Windows machine**
(e.g. a ~$10/month Windows VPS) running the same, unchanged code.

**The pieces:**
- `src/execution/mt5.py` — the handler (imports MetaTrader5 *lazily*, so importing
  it on macOS never crashes; converts units ↔ lots).
- `src/execution/mt5_service.py` — the small server that runs on the Windows machine
  and does what the engine asks over the network.
- `src/execution/remote_mt5.py` — the engine's side of that network link.
- **Security:** set the same `MT5_RPC_TOKEN` on both sides and the server refuses
  anyone without it. The link is plain TCP (not encrypted), so keep the port private
  (home network, VPN or SSH tunnel) as well.
- `docker/mt5/` — the Wine container, kept only as the documented dead end.

**Key terms:**
- **Wine** = runs Windows apps on Linux (didn't work for MT5's Python link).
- **xvfb** = a fake invisible screen so GUI apps can run headless.
- **RPC** = "remote procedure call": asking another machine to run a function.
- **Lazy import** = only load a library at the moment it's used, not at startup.

---

## Module 9 — Streamlit Dashboard (`dashboard/`)

**Job:** A simple web page to control and watch the system — no coding needed.

**In simple terms:** The "control panel." Instead of running scripts, you open a
browser, type settings, click a button, and see charts. Built with **Streamlit**,
which turns a Python script into a web app automatically (no React/HTML needed).

**What it lets you do:**
- **Enter MT5 demo credentials** (login, password, server) — typed in the browser,
  shown only as ●●● for the password, **never saved to code or git** (§9 safety).
- **Adjust parameters with sliders** — the +1.5 volume threshold, the ML confidence
  threshold, and risk-per-trade — then re-run instantly to see the effect.
- **Backtest mode** — click "Run Backtest": it loads data, trains the model the same
  way the scripts do (so the default settings reproduce the documented numbers), and
  shows the four §8 metrics with pass/fail, the win-rate confidence range, the
  **equity curve**, the **trade list** (with open/close times and exit reasons), and
  the model's **feature importances**.
- **Live mode** — send a single manual order through whichever handler
  `EXECUTION_HANDLER` selects: paper (mock, the default — fills at the reference price
  you type) or the real MT5 demo via the Windows machine. It shows the connection
  status first and never crashes if MT5 isn't running. Not an auto-trader.

**How it's built (a tidy split):** all the real work lives in `dashboard/service.py`
(plain Python functions, fully unit-tested). `dashboard/app.py` is just the thin UI
that calls them. The app itself was also driven end-to-end with Streamlit's test
harness.

**Run it:** `.venv/bin/python -m streamlit run dashboard/app.py`

---

## Module 10–11 — Docker + the RPC link

- `docker/engine/Dockerfile` + `docker-compose.yml` — the engine and dashboard in a
  small Linux container (no Wine, no MetaTrader5). `docker compose up engine` starts
  it; it shares `data/` and `models/` with your Mac so it uses the same cached data.
- The Live link (Module 8) is a tiny JSON-over-TCP protocol (`rpc_protocol.py`) so
  the engine container can talk to the Windows MT5 machine without ever importing
  MetaTrader5.

---

## What's next

- Decide whether to keep the current default or switch to a variant (see
  `docs/todo.md` §14 — the label/trade alignment results and the no-skill baseline
  bear on that choice).
- Apply the corrections listed in `docs/REPORT_CORRECTIONS.md` to Chapters 1–3.
- Write Chapters 4 and 5 from `docs/RESULTS.md` and `docs/STRATEGY_CONFIGS.md`.

---

## The non-negotiable rules baked into the code (quick reference)

| Rule | Why | Where enforced |
|------|-----|----------------|
| Random Forest only, no deep learning | CPU-friendly, transparent, resists overfit | `ml_model.py`; test scans all code + requirements |
| Chronological 80/20 split, never shuffle | Shuffling = training on the future (leakage) | `preprocessor.py`, `settings.SHUFFLE=False` |
| TimeSeriesSplit for tuning, never KFold | KFold shuffles → leakage | `ml_model.py` |
| Trade only if Volume Z > +1.5 **AND** model confident | Filters noise, fewer false trades | `signal_generator.py` |
| Demo account only, secrets in `.env` | Safety; never risk real money / leak creds | `settings.py`, `.env` |
| All thresholds in `config/settings.py` | No magic numbers scattered around | `config/settings.py` |
| Engine never imports MetaTrader5 | Lets everything run/test on macOS | `execution/` interface |
