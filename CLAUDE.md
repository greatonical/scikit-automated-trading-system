# CLAUDE.md

Operating guide for Claude Code in this repo. Read this first, then `docs/todo.md`.

## What this project is

A self-hosted automated Forex trading system: **statistical Z-Score filtering + a
scikit-learn Random Forest classifier**, backtested on held-out data, with a Streamlit
dashboard and a Docker deployment. It is a **B.Sc. Computer Science final-year project**
("Design and Implementation of an Automated Financial Trading System", Awosusi Gabriel
Ayomide, CSC/2019/079), so **defensibility and honest measurement matter more than
performance**. A suspiciously good number is a bug, not a win.

Three authorities, in precedence order:

1. `README.md` — the canonical build spec (§ numbers referenced throughout the code).
2. `GABRIEL_AWOSUSI_PROJECT_REPORT_CHAPTER_1-3.md` — the academic write-up
   (background/justification only), current as of 2026-09-17. Where it disagrees with
   the README, README wins. Known factual errors in it are listed in
   `docs/REPORT_CORRECTIONS.md` (listed for the author to apply; never edit the report).
3. `docs/` — the living record of what was actually built, measured, and decided.

## Hard constraints — never violate

- **Random Forest only.** No `tensorflow`, `keras`, `torch`, LSTM, or any neural net —
  not in code, imports, or any `requirements*.txt`. (`test_no_deep_learning_anywhere`
  scans all of them.)
- **Chronological 80/20 split, never shuffled.** `settings.SHUFFLE = False`. Shuffling a
  time-series = training on the future = data leakage.
- **Cross-validation uses `TimeSeriesSplit`, never `KFold`.** Tuning happens on the
  training set only; the test set stays sealed until the final measurement.
- **Features look backward, only the label looks forward.** Every indicator/Z-Score must
  be strictly trailing. Anti-leakage tests exist for each — keep them passing.
- **Hybrid AND-gate:** trade only when Volume Z-Score `>` 1.5 **AND** RF probability
  clears the confidence threshold. Either fails → HOLD. Strict `>`, never `>=`.
- **No magic numbers.** Every threshold, ratio, target, grid, cost and param lives in
  `config/settings.py`. Nothing in `src/` hardcodes one.
- **The engine never imports `MetaTrader5`.** It depends on the abstract
  `ExecutionHandler` only. Two tests assert `MetaTrader5` is absent from `sys.modules`.
- **Mock ↔ real execution swap = one config change** (`EXECUTION_HANDLER`), nothing else.
  It routes the dashboard's Live mode through the factory (`mock` = paper,
  `remote_mt5`, `mt5`). Backtests always use the mock, by design.
- **Volume is in units of base currency across the `ExecutionHandler` interface.**
  Only `MT5ExecutionHandler` converts to broker lots.
- **Demo MT5 account only.** Credentials live in the gitignored `.env`, never hardcoded,
  never committed, never printed.
- **`MetaTrader5` stays out of `requirements.txt`** (Windows-only). It lives in
  `requirements-mt5.txt`.

## Layout

```
config/settings.py        single source of truth for every tunable value (most env-overridable)
src/data_handler.py       yfinance fetch + clean (UTC) + 1h parquet cache; 4h derived at load (Module 1)
src/preprocessor.py       Z-Scores, indicators, triple-barrier labels, chronological split (Module 2)
src/ml_model.py           RandomForest train/tune/persist(+provenance)/predict_proba (Module 3)
src/signal_generator.py   hybrid AND-gate → BUY/SELL/HOLD + decision log (Module 4)
src/risk_manager.py       fixed-fractional sizing, dynamic stops (shared helper), hard limits (Module 5)
src/execution/base.py     abstract ExecutionHandler contract (Module 6)
src/execution/mock.py     in-memory broker sim w/ spread, slippage, SL/TP (Module 6)
src/execution/factory.py  config-driven handler selection (mock|mt5|remote_mt5)
src/execution/mt5.py      real MetaTrader5 handler, units→lots — Windows host only (Module 8)
src/execution/mt5_service.py   RPC server on the MT5 host, optional token (Module 11)
src/execution/remote_mt5.py    RPC client, runs in the engine (Module 11)
src/execution/rpc_protocol.py  JSON-over-TCP message format + token check (Module 11)
src/backtester.py         event-driven replay, optional time exit, §8 metrics + Wilson CI (Module 7)
dashboard/service.py      all dashboard logic, unit-tested, no Streamlit imports
dashboard/app.py          thin Streamlit UI shell (Module 9)
scripts/run_backtest.py   the canonical end-to-end evaluation run (saves the model)
scripts/sweep_winrate.py  SL/TP exit-geometry frontier + realised R:R (Step E)
scripts/tune_thresholds.py 60/20/20 val-tuned threshold search (Step C)
scripts/baseline_noskill.py same exits, random/fixed direction — how much is the model?
scripts/inspect_model.py  human-readable view of models/*.pkl incl. provenance
scripts/make_progress_docx.py one-off: renders the June progress report (needs python-docx)
docker/engine/            engine + dashboard image (Linux Python, no Wine)
docker/mt5/               Wine + xvfb + MT5 image — documented DEAD END, see below
tests/                    218 tests, all passing
```

## Commands

Full setup + runbook for a human (dashboard walkthrough, mock vs live, troubleshooting):
`docs/COMMANDS.md`.

```bash
.venv/bin/python -m pytest -q                          # 218 pass, 2 network deselected
.venv/bin/python -m pytest -m network -v               # live Yahoo smoke tests
.venv/bin/python scripts/run_backtest.py EURUSD 1h     # canonical evaluation (also GBPUSD, 4h)
.venv/bin/python scripts/sweep_winrate.py EURUSD 1h    # exit-geometry frontier
.venv/bin/python scripts/baseline_noskill.py EURUSD 1h # no-skill baseline
.venv/bin/python scripts/tune_thresholds.py EURUSD 1h  # Step C
.venv/bin/python scripts/inspect_model.py              # read the saved models in plain text
.venv/bin/python -m streamlit run dashboard/app.py     # dashboard on :8501
docker compose up engine                               # backtest only, no Wine
docker compose --profile live up                       # + mt5 container (see DEAD END)
```

Config knobs are env-overridable, so experiments are one-liners, e.g.
`DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 USE_RSI=true .venv/bin/python scripts/run_backtest.py EURUSD 1h`.
Every row in `docs/RESULTS.md` has its command in the Reproducibility table. Note that
`run_backtest.py` overwrites `models/random_forest_<PAIR>_<TF>.pkl` — re-run the default last.

Python is 3.14 in `.venv` (spec says 3.10+; 3.14 satisfies it).

## Current state (verified 2026-09-15)

- **Modules 1–11 complete**, 218 tests pass, everything documented in `docs/`.
- **Improvement phase A–E complete + full audit done** (`docs/AUDIT_2026-09-15.md`).
  Default config = triple-barrier label (Step A) + close-TP exits (Step E, `SL 1.2% / TP 0.4%`).
- Held-out results with costs, 1h (test 20 Jan → 12 Jun 2026):
  **EUR/USD 73.3% win [55.6–85.8] / PF 1.34 / DD 1.5%**,
  **GBP/USD 78.4% win [62.8–88.6] / PF 1.62 / DD 2.5%**. Win-rate and drawdown targets
  pass on both (EUR/USD only on the point estimate); **Sharpe fails on every config**
  (per-trade 0.1–0.4).
- **Three measured caveats on the default** (docs/RESULTS.md): (1) random trade direction
  with the same exits wins 67–69% — the model's edge is in profit factor, not win rate;
  (2) label ≠ trade (long-only 24-bar label vs long + short trades held to SL/TP); fully
  aligned via `USE_TIME_EXIT` / `LABEL_DYNAMIC_SL` / `ALLOW_SHORTS`, the strategy loses
  on both pairs; (3) ~30 trades per pair → wide intervals.
- **Default decided (2026-09-17):** the close-TP config **stays** the shipped default (it
  is the only one meeting the report's win-rate target on both pairs). Quote it with its
  caveats, and use the **far-TP** config wherever the question is whether the model itself
  has skill (it beats every random-direction seed). The alignment switches stay off.
  Don't change defaults without being asked.
- **4h** (rebuilt from 1h at load time): EUR/USD loses, GBP/USD profitable — mixed; 1h is primary.
  (The old "4h makes zero trades" was a stale zero-volume cache, now fixed.)
- **Module 12 (live MT5) is a resolved dead end under Wine.** `mt5.initialize()` fails
  `-10005` (IPC timeout) even on native x86 — proven by the sibling project `gadel-engine`
  (`docs/debug/MODE_B_WINE_RETROSPECTIVE.md` there). **Do not retry Wine.** Read
  `docs/WINE_VERDICT.md` before touching `docker/mt5/`. Deployment path: native Windows
  host running `python -m src.execution.mt5_service`, engine on `EXECUTION_HANDLER=remote_mt5`
  with a shared `MT5_RPC_TOKEN`.
- **Under version control.** Branch `main`, remote `origin` →
  `github.com/greatonical/scikit-automated-trading-system`. `.env`, `models/` and
  `logs/` stay ignored (`.env` has never been committed — verified 2026-09-17), but the
  cached `data/*_1h.parquet` are force-added on purpose: every documented number depends
  on that exact window.
- **Chapters 4 and 5 of the report are unwritten.** Material is in `docs/RESULTS.md` and
  `docs/STRATEGY_CONFIGS.md`; Chapters 1–3 corrections are in `docs/REPORT_CORRECTIONS.md`.

## Known gaps (tracked facts — don't "fix" silently)

- **Execution latency (< 500 ms) has never been measured against a broker.** The dashboard's
  Live mode records `latency_ms` per manual order, but no live MT5 run exists;
  `BacktestResult.meets_targets()` checks 4 of the 5 metrics. Report Scenario C is untested.
- **Sharpe is per-trade and unannualised** (`Backtester._sharpe`). The report's > 1.0 target
  conventionally refers to an annualised figure. State the convention wherever it appears.
- **`SIGNAL_LOG_FILE` and `LOG_LEVEL` are defined but unused.** Signal decisions go to the
  Python logger only.
- Cached 1h parquet in `data/` dates from 2026-06-14. Documented numbers depend on it;
  `force_refresh=True` will shift the window and the numbers. There is no 4h cache by design.

## Working style for this repo

- **Measure, don't assume.** Every strategy change gets a full backtest on **both** pairs,
  and the result — including negative ones — goes into `docs/RESULTS.md` with its command.
- Quote every win rate with its confidence interval, and keep the no-skill baseline next
  to headline win rates.
- One change at a time, re-baselined against the current default, so the cause-and-effect
  table stays clean for the evaluation chapter. Keep reverted experiments' code and their
  `USE_*=false` defaults.
- Before a refactor that shouldn't change behaviour, snapshot the trade lists and diff after.
- Add tests as you build; anti-leakage and label↔trade assertions are the most valuable.
- Keep docs honest and in sync. An unflattering measured number that is explained is worth
  more than a good number that can't be defended in a viva.
