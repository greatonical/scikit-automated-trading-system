# Build To-Do — Automated Financial Trading System

Derived from `README.md` (canonical build spec). The academic report
(`GABRIEL_AWOSUSI_PROJECT_REPORT_CHAPTER_1-3_corrected.md`) is background/justification only.
Build strictly in README §10 order, one module at a time, writing tests as we go.

**Golden rule:** prove the entire engine end-to-end against `MockExecutionHandler`
(via the Backtester) BEFORE touching any real MT5 / Wine / Docker work. The container is
the last mile and must never block the engine or the backtest results.

**Companion docs:**
- `docs/HOW_IT_WORKS.md` — plain-English explanation of every module.
- `docs/RESULTS.md` — backtest win-rate table per improvement step (updated each step).
- `docs/DEVIATIONS_FROM_SPEC.md` — every change vs the README/report, with reasons.
- `docs/RECOMMENDATIONS.md` — weaknesses + how to improve.
- `docs/TRIPLE_BARRIER_EXPLAINED.md`, `docs/MT5_INTEGRATION_PLAN.md`, `docs/MT5_CONTAINER_TESTING.md`.
- `docs/STRATEGY_CONFIGS.md` — the three exit profiles side by side.
- `docs/WINE_VERDICT.md` — why live MT5 needs native Windows.
- `docs/AUDIT_2026-09-15.md` — full audit: findings, fixes, evidence.
- `docs/REPORT_CORRECTIONS.md` — factual corrections to apply to Chapters 1–3.

---

## Hard constraints (never violate — check every PR against these)

- [ ] Predictive engine is **Random Forest (scikit-learn) ONLY**. No `tensorflow`, `keras`, `torch`, or any LSTM / neural-net code — not in imports, code, or `requirements.txt`.
- [ ] **Chronological 80/20 train/test split, NO shuffling** (financial time-series → shuffling = data leakage).
- [ ] Cross-validation uses **`TimeSeriesSplit`**, never default `KFold`.
- [ ] Hybrid signal fires only when **BOTH**: Volume Z-Score **> +1.5** AND RF bullish probability **> confidence threshold**. Either fails → **hold**.
- [ ] **Demo MT5 account only.** Credentials in `.env` (gitignored) + `.env.example` placeholders. Never hardcoded, never committed.
- [ ] **No magic numbers.** All thresholds/targets/params live in `config/settings.py`.
- [ ] Analytical engine, SignalGenerator, RiskManager, Backtester depend on the abstract `ExecutionHandler` only — never import `MetaTrader5` directly.
- [ ] `MetaTrader5` kept OUT of core `requirements.txt`; lives in `requirements-mt5.txt` (Wine container only). Core `requirements.txt` stays macOS-installable.
- [ ] Mock ↔ real execution swap = one config change, nothing else.
- [ ] Every signal decision logged (rule result + ML probability + final action) for transparency / viva defence.

---

## Phase 0 — Project scaffold ✅ DONE

- [x] Create directory structure per README §4.
- [x] `config/settings.py` — pairs (EUR/USD, GBP/USD), timeframes (1h, 4h), history (2019–2024), Z-Score rolling window, volume Z threshold (+1.5), ML confidence threshold, 80/20 split ratio, RF hyperparams, risk params (fixed-fractional %, daily loss limit, max drawdown < 15%, SL latency 500 ms), eval targets (win rate > 60%, profit factor > 1.5, Sharpe > 1.0), execution-handler selector (mock/mt5).
- [x] `requirements.txt` — core, macOS-installable, NO MetaTrader5.
- [x] `requirements-mt5.txt` — MetaTrader5 + Windows-side deps (Wine container only).
- [x] `.env.example` — blank MT5 LOGIN / PASSWORD / SERVER placeholders.
- [x] `.gitignore` — `.env`, `models/`, `data/`, `__pycache__`, etc.
- [x] `src/__init__.py`, `src/execution/__init__.py`, `config/__init__.py`, `tests/__init__.py`, `conftest.py`, `pytest.ini`.
- [x] `.venv` created; full core stack installs on Python 3.14 (numpy 2.4.6, pandas 3.0.3, sklearn 1.9.0, yfinance 1.4.1).

**Data-coverage decision (recorded):** yfinance caps intraday history at ~730 days, so 1h/4h cannot span 2019–2024. DataHandler fetches the deepest intraday window Yahoo allows and logs the ACTUAL coverage; timeframe (1h/4h, the load-bearing axis for the volume-Z hybrid logic) is preserved over history depth. 4h is resampled from 1h (no native Yahoo 4h bar). All timeframe/date values are config-driven.

---

## Module build order (README §10)

### 1. DataHandler — `src/data_handler.py` ✅ DONE
- [x] Connect to Yahoo Finance via `yfinance` (live fetch verified).
- [x] Fetch OHLCV for EUR/USD & GBP/USD at 1h and 4h (4h resampled from 1h; intraday clamped to ~730d, actual coverage logged).
- [x] Cache datasets to `data/` (parquet, gitignored; csv fallback).
- [x] `tests/test_data_handler.py` — 13 tests pass + 1 live-network smoke test (deselected by default).

### 2. Preprocessor — `src/preprocessor.py` ✅ DONE
- [x] Clean data (sort/dedupe/NaN — also done in DataHandler; transform re-sorts defensively).
- [x] Compute **rolling/trailing** Z-Score for Close and Volume (window from config; flat-window → 0, no inf).
- [x] Assemble feature set: O, H, L, C, Volume, Z(Close), Z(Volume).
- [x] Build binary labels: class 1 = bullish continuation (forward horizon), class 0 = bearish/neutral; Target never a feature.
- [x] Chronological 80/20 split, no shuffling (every train ts < every test ts).
- [x] `tests/test_preprocessor.py` — 13 tests pass, incl. anti-leakage: Z-Score strictly trailing, label forward-looking, split no-shuffle/no-overlap.

### 3. MLModel — `src/ml_model.py` ✅ DONE
- [x] `RandomForestClassifier` (params from config; random_state=42, n_jobs=-1).
- [x] Hyperparameter tuning via CV on **training set only**, using `TimeSeriesSplit` (GridSearchCV).
- [x] Persist model to `models/` with `joblib` (save/load round-trips to identical predictions).
- [x] Expose `predict_proba` (returns P(bullish=class 1) in [0,1]).
- [x] Final eval on held-out test set only; feature_importances() for transparency.
- [x] `tests/test_ml_model.py` — 12 tests pass: TimeSeriesSplit (not KFold) asserted, tune-only-on-train, proba range, persistence round-trip, no-DL-imports.

**✅ Volume data source — RESOLVED.** Spot FX (`=X`) reports volume=0. Fix: price from spot, volume from matching CME FX futures (`6E=F`/`6B=F`) aligned by timestamp (`USE_FUTURES_VOLUME` + `VOLUME_SOURCE` in settings; falls back to spot volume on fetch failure). Verified on live data: volume nonzero ~88% of candles, `ZScore_Volume` importance 0.00 → ~0.16, +1.5 gate fires ~13% of test rows. 4 new merge tests + 1 live test. Documented in `docs/HOW_IT_WORKS.md`.

### 4. SignalGenerator — `src/signal_generator.py` ✅ DONE
- [x] Hybrid logic: Volume Z-Score > +1.5 AND RF bullish prob > threshold → trade; else hold (strict `>`, both gates).
- [x] Direction from ML probability (high→BUY, low→SELL); volume rule is the gate.
- [x] Log each decision (rule result + probability + action); `Signal` dataclass + `to_frame()` for transparency.
- [x] `tests/test_signal_generator.py` — 11 tests pass: full truth table, boundary (exactly-at-threshold holds), batch, config thresholds.
- [x] Explained in `docs/HOW_IT_WORKS.md`.

### 5. RiskManager — `src/risk_manager.py` ✅ DONE
- [x] Fixed-fractional position sizing (% of equity; scales down as equity falls).
- [x] Dynamic stop-loss: tightens (× factor) when |Z-Score| ≥ trigger; correct stop/target per BUY/SELL.
- [x] Hard limits: daily loss limit + max drawdown ceiling (< 15%) via `can_trade()`; equity/peak tracking.
- [x] `tests/test_risk_manager.py` — 17 tests pass (sizing, dynamic stop, limits, day reset).
- [x] Explained in `docs/HOW_IT_WORKS.md`.

### 6. ExecutionHandler interface + MockExecutionHandler ✅ DONE
- [x] `src/execution/base.py` — abstract `ExecutionHandler` (connect / place_order / get_open_positions / close_position / disconnect) per §13.
- [x] `src/execution/mock.py` — pure-Python sim (in-memory positions, unique tickets, simulated fills, spread/slippage, SL/TP bar-by-bar exits, P&L). No MT5/Wine/Docker.
- [x] `src/execution/factory.py` — config-driven mock↔mt5 swap (`EXECUTION_HANDLER`); MT5 imported lazily so macOS never loads MetaTrader5.
- [x] `tests/test_mock_execution.py` — 22 tests pass (contract, fills, P&L, spread/slippage, SL/TP, factory, no-MT5-import).
- [x] Explained in `docs/HOW_IT_WORKS.md`.

### 7. Backtester — `src/backtester.py` ✅ DONE
- [x] Run on held-out test set against `MockExecutionHandler` (spread+slippage modelled).
- [x] Produce §8 metrics: Win Rate, Max Drawdown, Profit Factor, Sharpe, net P&L, trade count + pass/fail vs targets.
- [x] Validate §8 scenarios: ranging (zero trades), low-confidence (no trades), forced win/loss, cost realism.
- [x] `tests/test_backtester.py` — 11 tests pass. Plus `scripts/run_backtest.py` for real end-to-end runs.
- [x] Fixed daily-loss baseline reset per calendar day (was halting forever). Added `price` to abstract interface for clean mock/MT5 contract.
- [x] **MILESTONE: full engine proven end-to-end on mock. 103 tests pass.**

**📊 Honest backtest result (held-out ~2024-2026 data, with costs):** Strategy does NOT meet the §8 profit targets — EURUSD 1h: win rate 26%, profit factor 0.88, net −$215; GBPUSD 1h: win rate 19%, PF 0.70, net −$939. Max drawdown PASSES (<15%) on both, confirming risk management works. This is the expected outcome of a thin (~52%) edge meeting real costs, and is a valid, reportable result (see `docs/RECOMMENDATIONS.md`). Improving it = feature engineering / threshold tuning / better volume data (future work), NOT a code bug.

### 8. MT5ExecutionHandler (LAST) — `src/execution/mt5.py` + `docker/mt5/` ✅ DONE
- [x] Real impl of the interface, imports `MetaTrader5` (lazily, in connect()), container-only.
- [x] Connect to MT5 demo headless under Wine + `xvfb` (entrypoint.sh), portable/single instance.
- [x] Route orders (BUY@ask/SELL@bid), get positions, close by ticket — mapped onto our contract.
- [x] `docker/mt5/Dockerfile` — tobix/pywine base + Python-in-Wine-prefix + xvfb; `mt5_service.py` entrypoint.
- [x] Clean boundary: `mt5_service.py` is the documented container entrypoint (connect + idle heartbeat).
- [x] Memory limits in `docker-compose.yml` (≤1g); validated `docker compose config`.
- [x] `tests/test_mt5_execution.py` — 14 tests pass (fake MT5 module): API mapping + macOS-safe import (MetaTrader5 never loaded).
- [x] Explained in `docs/HOW_IT_WORKS.md`. **124 tests pass total.**

### 9. Streamlit dashboard — `dashboard/app.py` ✅ DONE
- [x] Credential input (MT5 login/password/server) — typed in browser, password masked, never hardcoded/committed.
- [x] Parameter controls (volume threshold, ML confidence, risk per trade) via sliders.
- [x] Performance: 4 §8 metrics w/ pass-fail, equity curve, trade table, feature importances.
- [x] Logic split into `dashboard/service.py` (unit-tested) + thin `dashboard/app.py` UI.
- [x] `tests/test_dashboard_service.py` — 7 tests pass (incl. password never leaked). App verified serving HTTP 200.
- [x] Explained in `docs/HOW_IT_WORKS.md`. Run: `.venv/bin/python -m streamlit run dashboard/app.py`

### 10. Dockerise ✅ DONE
- [x] `docker/engine/Dockerfile` — engine + dashboard (Linux Python, no Wine/MT5).
- [x] `docker-compose.yml` — engine (always) + mt5 (behind `live` profile, single instance), shared `ats` network.
- [x] `docker-compose.dev.yml` / `docker-compose.prod.yml` — both headless; dev generous-but-realistic, prod tight (README §13 limits).
- [x] All three compose configs validate; `live` profile correctly gates mt5 (backtest never starts Wine container).

### 11. Live MT5 RPC integration (engine ↔ mt5 container) ✅ DONE
- [x] `src/execution/rpc_protocol.py` — tiny JSON-over-TCP protocol.
- [x] `src/execution/mt5_service.py` — RPC SERVER in the mt5 container (wraps MT5ExecutionHandler, single terminal).
- [x] `src/execution/remote_mt5.py` — `RemoteMT5ExecutionHandler` RPC CLIENT in the engine (stdlib socket only, macOS-safe, graceful when down).
- [x] Factory `remote_mt5` option; `MT5_RPC_HOST/PORT` in settings.
- [x] Dashboard: Backtest (mock, default, no MT5) vs Live (MT5 demo) mode selector; manual single-shot order; graceful "service unreachable" message.
- [x] `tests/test_rpc_execution.py` — 12 tests (real socket, fake handler) + 2 dashboard live tests. **138 tests pass total.**
- [x] Design in `docs/MT5_INTEGRATION_PLAN.md`.

### 12. Build + verify the live MT5 container (MOSTLY DONE — blocked on terminal binary)
Attempted on arm64 Mac 2026-06-18. Most of it works; one blocker remains.
- [x] Build the Wine/MT5 image — needed `--platform=linux/amd64` (tobix/pywine is x86-only; arm64 emulates). Added to Dockerfile + compose.
- [x] Real HFMarkets demo creds added to `.env`; load correctly.
- [x] Container runs stably; xvfb + Wine boot; **RPC service listens on 9099**; `ping → pong` round-trip works.
- [x] **MetaTrader5 lib imports under Wine** — fixed by pinning `numpy==1.26.4` (numpy 2 calls `ucrtbase.dll.crealf`, unimplemented in this Wine → aborts). MT5 deps installed LAST so the pin wins.
- [x] Fixed: PYTHONPATH (`src` import), stale X-lock clear, module-form launch.
- [x] Documented full status + finish-later options in `docs/MT5_CONTAINER_TESTING.md`.
- [x] **RESOLVED: Wine is a proven dead end → native Windows is the deployment host.** `mt5.initialize()` can't work under Wine (terminal's IPC subsystem never starts → `-10005`), confirmed by sibling project `gadel-engine` on native x86 + CI + a byte-for-byte clone of a working reference; native Windows works first try (real trade placed). Full finding + native-Windows recipe in **`docs/WINE_VERDICT.md`**. Wine artifacts kept as documented dead-end.

> Impact on the project: NONE. Full engine + evaluation + §8 results run on the mock
> (the architecture isolates the live broker as the "last mile"). Live execution is a
> deployment detail: run the existing `MT5ExecutionHandler` + RPC server on a native
> Windows host (~$10/mo VPS), unchanged.

---

## Evaluation targets (README §8 — verify in backtest)

| Metric            | Target   |
| ----------------- | -------- |
| Win Rate          | > 60%    |
| Maximum Drawdown  | < 15%    |
| Execution Latency | < 500 ms |
| Profit Factor     | > 1.5    |
| Sharpe Ratio      | > 1.0    |

---

## 13. Win-rate improvements (PLANNED — build one at a time, measure after each)

Baseline (held-out, with costs): EURUSD 1h win 26%/PF 0.88; GBPUSD 1h 19%/PF 0.70;
drawdown passes. Plan agreed 2026-06-15 — re-run `scripts/run_backtest.py` on BOTH
pairs after every step to build a cause-and-effect table for the report.

- [x] **A. Triple-barrier label** ✅ — class 1 = TP hit before SL within max_hold bars. **Both pairs flipped from loss to profit:** EURUSD win 26%→37%, PF 0.88→1.42, net −$215→+$576; GBPUSD win 19%→50%, PF 0.70→2.42 (PASS), net −$939→+$1307. Drawdown improved on both. Config: `LABEL_METHOD`, `TRIPLE_BARRIER_MAX_HOLD`. Doc: `docs/TRIPLE_BARRIER_EXPLAINED.md`. 8 new tests.
- [x] **B1. + RSI** ❌ REVERTED — hurt both pairs (EURUSD win 37%→32%/PF 1.42→1.17; GBPUSD 50%→38%/PF 2.42→1.49). `USE_RSI=false` default, code kept. Useful negative result. Baseline stays Step A.
- [x] **B2. + MACD** ❌ REVERTED — hurt badly: both pairs net loss, drawdown breached 15% (EURUSD 23%/PF 0.78; GBPUSD 26%/PF 0.87), trades ~doubled. `USE_MACD=false`. Baseline stays Step A.
- [x] **B3. + ATR** ❌ REVERTED — feature ~neutral (EURUSD identical, GBPUSD mixed); ATR-based stops harmful at every multiple (1h ATR too small → over-tight stops, trades exploded, DD>15%). Kept flat-% stops. `USE_ATR`/`USE_ATR_STOPS`=false. Baseline stays Step A.
- [x] **B4. + Higher-timeframe trend** ❌ REVERTED (not robust) — HELPED EURUSD (PF 1.42→1.78, +$1,613) but HURT GBPUSD (PF 2.42→1.04, near break-even). Doesn't generalise across pairs. `USE_HTF_TREND=false` default. Baseline stays Step A.
- [x] **C. Threshold tuning** (60/20/20 train/val/test, tuned on val, reported on test — `scripts/tune_thresholds.py`) — **re-measured 2026-09-15** after fixing a relabelling bug (the script traded SL/TP values the model wasn't trained on): EURUSD test PF 1.76 / win 31% on 13 trades; GBPUSD's best validation combo was itself unprofitable (val PF 0.98) → test PF 1.13. (Old numbers PF 2.68 / 1.15 withdrawn.) Tuning rests on too few validation trades; robust default stays untuned.
- [x] **D. + Time-of-day/session** ❌ REVERTED — originally measured with London-time hours (EUR PF 1.42→1.56, GBP 2.42→1.97); **re-measured 2026-09-15 with UTC hours**: EUR 1.42→1.72, GBP 2.42→1.96. Same conclusion — doesn't improve both. `USE_TIME_FEATURES=false`.
- [x] **★ E. Win-rate-first exits (SL 1.2% / TP 0.4%) — ADOPTED AS DEFAULT.** Close TP + wide stop → win rate **73.3% (EUR) / 78.4% (GBP)**, both CLEAR §8 >60% target, still profitable (PF 1.34/1.62, DD <3%). Honest, leakage-free (label + RiskManager share SL/TP). Trade-off (smaller reward/trade) + full sweep in `docs/RESULTS.md`. `scripts/sweep_winrate.py`.

**✅ IMPROVEMENT PHASE COMPLETE (A–D 2026-06-16, E 2026-06-18).** Default config = **Step A (triple-barrier label) + Step E close-TP exits (SL 1.2% / TP 0.4%)**. Triple-barrier was the decisive change (loss→profit both pairs); no indicator improved both pairs; threshold tuning rests on too few validation trades to trust (Step C re-measured 2026-09-15). Full table + conclusion in `docs/RESULTS.md`.

### ⏸ RESUME POINT (updated 2026-09-15)
Coding is complete; the 2026-09-15 audit fixed everything listed in §14 below. Next:
the §14 open decision (keep the default or switch), then the report corrections
(`docs/REPORT_CORRECTIONS.md`), then Chapters 4–5. Module 12 (live MT5) needs a
native Windows host, not Wine (`docs/WINE_VERDICT.md`).

Guardrails: backward-looking features only (no leakage); all knobs in `config/settings.py`;
Random Forest only; tune on train/val, never the test set; measure every step.

---

## 14. Audit fixes (2026-09-15) ✅ DONE — details in `docs/AUDIT_2026-09-15.md`

Full read of every doc, code file and test; each finding measured, then fixed and
re-measured on both pairs. Regression check: all pre-existing configs reproduce
trade-for-trade after the refactors. **210 tests pass.**

- [x] **4h "zero trades" explanation was wrong** — stale zero-volume 4h cache, not volume smoothing. 4h now rebuilt from 1h at load time (never cached); data-quality guard warns on < 50% nonzero volume. 4h re-measured: GBP profitable, EUR loses.
- [x] **Win rate vs geometry** — `scripts/baseline_noskill.py` added; random direction wins ~67–69% with the default exits. Wilson 95% CI now reported with every win rate (`WIN_RATE_CI_Z`).
- [x] **Realised > nominal R:R explanation was wrong** — cause is dynamic-stop tightening (bigger position), not TP overshoot. Corrected; sweep now prints tightened share + realised R:R.
- [x] **Label/trade mismatches** — switches `USE_TIME_EXIT`, `LABEL_DYNAMIC_SL`, `ALLOW_SHORTS` added, measured singly and together; alignment test + negative-control test added.
- [x] **Stale numbers** — Sharpe for Step E rows; PF 1.30 vs 1.34 (two tuning grids → one `EVAL_PARAM_GRID` shared by all scripts + dashboard); far-TP EUR row; B3b row was the 1.5×/3× run (5×/10× row added); Step D re-measured with UTC hours; Step C re-measured after fixing its relabelling bug.
- [x] `EXECUTION_HANDLER` now actually routes the dashboard's Live mode (mock = paper); backtests always mock (documented).
- [x] MT5 volume units — engine units → broker lots via `symbol_info`, rounded down.
- [x] Stale model removed; models saved per pair/timeframe with provenance; `inspect_model.py` shows it.
- [x] Timestamps normalised to UTC (were Europe/London).
- [x] SL/TP (and the dynamic-stop trigger) env-overridable → every documented row is a one-liner.
- [x] RPC shared-secret token (`MT5_RPC_TOKEN`); `allow_reuse_address` fixed.
- [x] Engine container mounts `data/` + `models/`.
- [x] Dashboard "Reference price" now used (paper fill price); Live mode records `latency_ms`.
- [x] Tautological no-deep-learning test replaced (scans all code + requirements); weak futures-off test strengthened.
- [x] Duplicate `PROGRESS_REPORT_2026-06-17 copy.md` removed; stale docs brought up to date.

**Open decisions / remaining work**
- [ ] **Choose the default.** Keep the unaligned close-TP default (win-rate target met, but win rate ≈ geometry and profit relies on untrained trade management), or switch to a variant with stronger evidence of model skill (e.g. far-TP: beats every random seed). Numbers: `docs/RESULTS.md` "No-skill baseline" + "Label/trade alignment".
- [ ] Apply `docs/REPORT_CORRECTIONS.md` to Chapters 1–3 (Word version).
- [ ] Write Chapters 4 and 5.
- [ ] Known gaps kept as-is: latency never measured live; Sharpe per-trade; `SIGNAL_LOG_FILE`/`LOG_LEVEL` unused; no git repo.

---

## Status

- [x] Read README.md + chapter report in full.
- [x] Modules 1–11 built, tested, documented in `docs/HOW_IT_WORKS.md`.
- [x] Honest backtest run (Module 7) → improvement phase A–E (§13) → audit (§14).
- [x] Module 12: live MT5 container — **resolved as a dead end**; deployment = native Windows host (`docs/WINE_VERDICT.md`).
- [x] Module 13: win-rate improvements (§13).
- [ ] §14 open decisions (default choice, report corrections, Chapters 4–5).
