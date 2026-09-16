# Deviations from the README / Project Spec

Honest log of every place the implementation differs from, or adds to, the
original README and chapter report — with the reason. Useful for the viva: you
can explain each decision rather than be surprised by it. None of these break the
README's hard constraints (Random Forest only, chronological no-shuffle split,
TimeSeriesSplit CV, hybrid AND-logic, demo-only, no magic numbers).

Last reviewed: 2026-09-15 (full audit — see `docs/AUDIT_2026-09-15.md`).

---

## Data

### 1. Intraday data range: ~2 years, not 2019–2024

- **Spec:** §5 asks for 1h/4h candles spanning 2019–2024 (5 years), test set ≈ mid-2023 → 2024.
- **Reality:** Yahoo Finance only serves intraday (≤1h) data for ~the last 730 days.
- **What we did:** fetch the deepest 1h window Yahoo allows and log the actual
  coverage. Cached window: mid-June 2024 → 12 June 2026. Held-out test set:
  **20 Jan → 12 Jun 2026** (~4.8 months, 2,456 hourly bars).
- **Why it's fine:** ~12,300 hourly candles per pair is ample to train a Random
  Forest; it's a real, citable data-source limit, not a design flaw. The report's
  Chapter 3 still quotes 2019–2024 — see `docs/REPORT_CORRECTIONS.md`.

### 2. Volume comes from CME FX futures, not spot

- **Spec:** §3.3.1 uses a Volume Z-Score > +1.5 gate ("institutional participation").
- **Reality:** spot FX (`EURUSD=X`) reports volume = 0 on Yahoo (no central exchange).
- **What we did:** take **price** from spot and **volume** from the matching CME FX
  futures (`6E=F`, `6B=F`), aligned by timestamp. Config: `VOLUME_SOURCE`,
  `USE_FUTURES_VOLUME`. A data-quality guard warns if < 50% of bars carry volume.
- **Why it's fine:** CME FX-futures volume is the standard proxy for institutional
  FX activity — exactly what the gate is meant to detect. Without it the +1.5 gate
  has no signal.

### 3. 4h is derived from 1h at load time; timestamps are UTC

- **Spec:** §5 lists 1h and 4h candles.
- **What we did:** yfinance has no 4h bar, so 4h is resampled from the cached 1h
  series every time it is requested and never cached on its own. All timestamps are
  normalised to UTC (Yahoo serves spot FX in Europe/London time).
- **Why:** a separately cached 4h file once went stale (saved before the futures
  volume fix, zero volume on every bar), which silently produced zero 4h trades.
  Measured 4h results are in `docs/RESULTS.md`; the system's primary timeframe is 1h.

## Model and labels

### 4. Triple-barrier label (added; replaces next-candle as default)

- **Spec:** describes class 1 = "bullish continuation" but doesn't fix the exact
  labelling rule.
- **What we did:** label each candle by whether take-profit is hit before stop-loss
  within 24 bars (triple-barrier), using the same SL/TP the RiskManager uses.
  Config: `LABEL_METHOD` (default `triple_barrier`), `TRIPLE_BARRIER_MAX_HOLD`. The
  original next-candle label is still available.
- **Why:** aligns the ML target with how trades resolve. Measured: flipped both pairs
  from net loss to net profit. Grounded in López de Prado (2018), already cited.
- **Caveat (measured 2026-09-15):** by default the label and the traded position still
  differ in three ways — see #6.

### 5. Exit profile: close take-profit (SL 1.2% / TP 0.4%) is the default

- **Spec:** §7 asks for stops but fixes no distances; Table 3.3 sets Win > 60%.
- **What we did (Step E):** chose the exit geometry that meets the report's win-rate
  target on both pairs. Two sounder-risk-reward alternatives are documented and
  one-line switchable (`docs/STRATEGY_CONFIGS.md`).
- **Caveat (measured):** most of that win rate comes from the geometry itself — random
  trade direction with the same exits wins ~67–69% (`scripts/baseline_noskill.py`).

### 6. Label and trade are not fully aligned (switches provided, off by default)

- **Spec:** implies the model predicts the trades the system takes.
- **Reality:** the label is long-only with a 24-bar horizon and a flat stop; trades
  are long and short, held until SL/TP, with a dynamically tightened stop.
- **What we did:** added `USE_TIME_EXIT`, `LABEL_DYNAMIC_SL` and `ALLOW_SHORTS`, a unit
  test proving outcome == label when aligned, and measured each switch. Fully aligned,
  the strategy loses on both pairs. Defaults unchanged pending the owner's decision
  (`docs/todo.md` §14). This is a design inconsistency, not leakage.

### 7. The SELL side is an extension of README §2

- **Spec:** §2 defines the ML gate on the bullish class ("class 1 vs bearish/neutral
  class 0").
- **What we did:** also SELL when P(bullish) < 1 − threshold (symmetric). `ALLOW_SHORTS=false`
  gives the literal long-only reading. Measured: long-only loses on the default config.

### 8. Features tested beyond the spec (all reverted)

The spec's feature set is OHLCV + Z(Close) + Z(Volume). Each extra feature was added
one at a time and measured on both pairs (`docs/RESULTS.md`); none improved both pairs,
so all are off by default with the code kept for reproducibility.

| Feature | In report? | Result |
|---------|-----------|--------|
| RSI | Yes (Chong/Cardoso citations) | B1 — hurt both pairs ❌ |
| MACD | Yes (Chong/Cardoso citations) | B2 — hurt badly, DD > 15% ❌ |
| ATR (feature / stops) | No | B3 — neutral / harmful ❌ |
| Higher-timeframe trend | No | B4 — helps EUR, hurts GBP ❌ |
| Time-of-day / session | No | D — helps EUR, hurts GBP ❌ |

## Execution and deployment

### 9. Execution layer: interface + Mock + MT5 + RPC client (per §13)

- **Spec:** §13 mandates an abstract `ExecutionHandler`, a Mock for macOS dev, and
  a real MT5 handler; the engine↔execution boundary is left open ("thin RPC/socket").
- **What we did:** exactly that, plus `RemoteMT5ExecutionHandler` (RPC client) so the
  engine can drive MT5 on another machine without importing MetaTrader5. The RPC
  server accepts an optional shared secret (`MT5_RPC_TOKEN`).
- **`EXECUTION_HANDLER` semantics:** it selects the handler for **live order routing**
  (the dashboard's Live mode, via the factory): `mock` = paper, `remote_mt5`, `mt5`.
  Backtests always use the mock — replay needs simulated fills at historical prices.
  (Until 2026-09-15 no runtime code read this setting.)
- **Volume units:** the engine sizes in units of base currency; `MT5ExecutionHandler`
  converts to broker lots via `symbol_info` (rounding down, rejecting below minimum).

### 10. Live MT5 runs on native Windows, not Wine-in-Docker

- **Spec:** §13 prescribes headless MT5 under Wine + xvfb in Docker.
- **Reality:** `mt5.initialize()` cannot work under Wine (`-10005` IPC timeout), proven
  on native x86 with no emulation; native Windows works first try.
- **What we did:** kept the Wine artifacts as a documented dead end; the deployment path
  is a Windows host running the unchanged handler + RPC server (`docs/WINE_VERDICT.md`).
- **Consequence:** the report's live-demo evaluation (objective 4, Scenario C) has not
  been run; all results come from the backtester.

### 11. Dashboard has Backtest vs Live modes

- **Spec:** §9 wants credential input, parameter controls, monitoring.
- **What we did:** Backtest (mock, default) and Live (manual single-shot orders through
  `EXECUTION_HANDLER` — paper by default). Not an auto-trader.
- **Why:** keeps backtesting fully usable without MT5, and makes live trading explicit
  and safe for a demo/viva.

### 12. Docker: two services + dev/prod profiles

- **Spec:** §10 step 10 says "Dockerise (Dockerfile + docker-compose.yml)".
- **What we did:** separate `engine` and `mt5` images; mt5 behind a `live` profile so
  backtesting never starts Wine; `docker-compose.dev.yml` / `.prod.yml` overrides; the
  engine mounts `data/` and `models/` so it uses the same cached window.

### 13. Python 3.14 (spec says 3.10+)

- **Reality:** the dev machine has Python 3.14; all core deps install and pass. The
  engine Docker image uses Python 3.12. Both satisfy "3.10+".

### 14. Config defaults chosen where the spec left them open

- `ML_CONFIDENCE_THRESHOLD = 0.55` (spec says "configured threshold", no value).
- `ZSCORE_WINDOW = 20`, `TRIPLE_BARRIER_MAX_HOLD = 24`, risk/SL/TP defaults.
- All live in `config/settings.py` (no magic numbers); most are env-overridable.

---

## Spec items not (yet) met — known gaps, not deviations

- **Execution latency (< 500 ms)** — never measured against a broker. The dashboard's
  Live mode now records `latency_ms` per manual order, but no live MT5 run exists.
  Scenario C (stop-loss within 500 ms) is untested.
- **Sharpe** — per-trade and unannualised (`Backtester._sharpe`); the > 1.0 target is
  conventionally annualised. State the convention wherever the number appears.
- **Signal log file** — decisions go to the Python logger; `SIGNAL_LOG_FILE` and
  `LOG_LEVEL` are defined but unused.
