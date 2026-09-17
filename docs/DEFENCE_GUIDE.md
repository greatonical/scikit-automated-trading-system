# Defence Guide — what to say, and how to run it live

Everything you need to defend the project in a viva and to demonstrate it on the spot.
Numbers here are the measured defaults (held-out test set 20 Jan → 12 Jun 2026, spread
and slippage included). Full evidence: `docs/RESULTS.md`; audit trail:
`docs/AUDIT_2026-09-15.md`.

---

## 1. The result in one breath

> "Hybrid system: a volume-anomaly rule and a Random Forest must agree before it trades.
> On held-out data with costs, EUR/USD wins 73.3% of trades with a profit factor of 1.34
> and a 1.5% maximum drawdown; GBP/USD 78.4%, 1.62 and 2.5%. Both clear the 60% win-rate
> and 15% drawdown targets. Sharpe does not, and I can explain exactly why the win rate
> is as high as it is."

| Metric | Target | EUR/USD | GBP/USD |
|--------|--------|---------|---------|
| Win rate | > 60% | **73.3%** ✅ [95% CI 55.6–85.8] | **78.4%** ✅ [62.8–88.6] |
| Profit factor | > 1.5 | 1.34 ❌ | **1.62** ✅ |
| Max drawdown | < 15% | **1.5%** ✅ | **2.5%** ✅ |
| Sharpe (per-trade) | > 1.0 | 0.13 ❌ | 0.22 ❌ |
| Trades / net P&L | — | 30 / +$257 | 37 / +$532 |

---

## 2. The questions you will be asked

**"Is that 73% win rate real?"** — *Yes, and most of it is the exit geometry, not the
model.* With a take-profit three times nearer than the stop, random buy/sell decisions on
the same candles already win 67–69% (`scripts/baseline_noskill.py`). The model's real
contribution is profit factor: 1.34 / 1.62 versus ~1.04 for random. And with 30 trades the
95% interval is 56–86%, so it's a point estimate, not a guarantee.
*(Volunteering this is the strongest thing you can do — you found and measured the
weakness in your own headline number.)*

**"Then where does the model clearly add value?"** — In the far-take-profit configuration
(SL 0.5% / TP 1.0%): it beats **every** random run on both pairs, on both win rate and
profit factor. Lower win rate (37–50%), much stronger evidence of skill, best profit
factor (2.42 on GBP/USD).

**"How do you know there's no data leakage?"**
- Chronological 80/20 split, never shuffled — every training candle precedes every test candle.
- Tuning uses `TimeSeriesSplit`, never `KFold`, and only on the training set.
- Features are strictly backward-looking; tests delete future rows and assert past
  feature values don't change.
- The test set is used once, at the end.

**"What was your biggest improvement?"** — Changing the question the model answers. The
first version predicted "will the next candle close higher?" and lost money. The
triple-barrier label asks "will the take-profit be hit before the stop-loss?" — the
question the strategy actually cares about. Both pairs flipped from loss to profit.

**"Did the standard indicators help?"** — No, and that's a documented result. RSI, MACD,
ATR, higher-timeframe trend and time-of-day were each added alone and measured on both
pairs. None improved both. The code is kept, switched off.

**"Your literature review talks about order blocks — where are they?"** — Implemented and
measured, then switched off on the evidence (Step F). A zone is created when a candle
*closes* beyond the recent swing, is filtered by ATR size, and dies when price trades back
into it; the model receives the distance to the nearest bullish and bearish zone plus an
"inside a zone" flag. The Random Forest genuinely used them — about 20% of total feature
importance — but they improved only GBP/USD at the default exits and hurt the other three
pair/config combinations, so they stay off. The most interesting detail: the "price is
inside a zone" flag, which is the part discretionary traders actually trade, scored 0.001
importance, because price is inside a live zone on only ~3.5% of bars. What the model used
was *proximity* to a zone, not the zone as a trigger.

**"Why Random Forest and not an LSTM?"** — CPU-only hardware, resistance to overfitting
through ensemble averaging, and interpretability via feature importances. Deep learning is
reviewed and rejected in Chapter 2, not ignored.

**"Why does Sharpe fail?"** — It's 0.13–0.22, and it's a per-trade figure, not annualised,
so it isn't directly comparable to the >1.0 benchmark. Stated as a limitation rather than
massaged.

**"Your label and your trades aren't the same thing, are they?"** — Correct, and I
measured it. The label is long-only with a 24-bar horizon; the system also sells and holds
until the stop or target. Three switches align them; fully aligned, the strategy loses on
both pairs. It's a design inconsistency, not leakage — no future data reaches any feature.

**"Why no live trading?"** — MetaTrader 5's Python API cannot initialise under Wine
(error −10005, an IPC timeout), proven on native x86 hardware and in CI, not just on my
Mac. Native Windows works first try. The handler, the RPC service and the dashboard's live
mode are built and unit-tested against a simulated MetaTrader 5; only the host changes.

**"What about the 4-hour timeframe?"** — It trades, but results are mixed: GBP/USD is
profitable (PF 1.76), EUR/USD is not (0.76). So 1h is the system's timeframe. Earlier the
4h data produced no trades at all, which turned out to be a stale cache with no volume —
found and fixed in the audit.

**"How much data?"** — Yahoo Finance caps hourly data at ~730 days, so the set runs
mid-June 2024 → 12 June 2026: ~12,300 hourly candles per pair, ~9,800 for training and
2,456 held out. That's a real data-source limit, and the report's Chapter 3 wording needs
updating to match (see `docs/REPORT_CORRECTIONS.md`).

**"Where does the volume come from? Spot FX has none."** — Correct: Yahoo reports zero for
spot. Price comes from spot, volume from the matching CME FX futures (6E=F, 6B=F), aligned
by timestamp — the standard institutional-activity proxy, which is exactly what the
volume gate is meant to detect.

---

## 3. Running it (demo-ready)

```bash
cd ~/Documents/Projects/BotsProjects/scikit-automated-trading-system

.venv/bin/python -m pytest -q                           # 218 pass, 2 network tests skipped
.venv/bin/python scripts/run_backtest.py EURUSD 1h      # the headline result
.venv/bin/python scripts/run_backtest.py GBPUSD 1h
.venv/bin/python scripts/baseline_noskill.py EURUSD 1h  # "is it the model?" check
.venv/bin/python scripts/sweep_winrate.py EURUSD 1h     # win rate vs reward trade-off
.venv/bin/python scripts/tune_thresholds.py EURUSD 1h   # honest threshold tuning (Step C)
.venv/bin/python scripts/inspect_model.py               # what's inside the saved models
.venv/bin/python -m streamlit run dashboard/app.py      # dashboard on :8501
docker compose up engine                                # same thing, containerised
```

Strategy changes need no code edit:

```bash
# far-TP profile — the clearest evidence of model skill
DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 .venv/bin/python scripts/run_backtest.py EURUSD 1h

# make the trades match the label exactly — shows the honest downside
USE_TIME_EXIT=true LABEL_DYNAMIC_SL=true ALLOW_SHORTS=false .venv/bin/python scripts/run_backtest.py EURUSD 1h
```

Every number in `docs/RESULTS.md` has its exact command in that file's Reproducibility
table. Note `run_backtest.py` overwrites `models/random_forest_<PAIR>_<TF>.pkl`, so re-run
the plain default last if you want the saved models to match the headline.

### Live / paper mode

The dashboard's Live tab routes orders through whatever `EXECUTION_HANDLER` selects:
`mock` (paper, the default — fills at the reference price you type, no MetaTrader 5
needed), `remote_mt5` (RPC to a Windows host running the terminal) or `mt5` (direct, on
that Windows host). Set `MT5_RPC_TOKEN` on both sides for the remote path.

---

## 4. A five-minute live demo

1. `.venv/bin/python -m pytest -q` → 218 passing tests (evidence of engineering rigour).
2. `.venv/bin/python -m streamlit run dashboard/app.py`, click **Run Backtest** → metrics
   with pass/fail, the win-rate confidence interval, equity curve, trade list with exit
   reasons, and feature importances.
3. `.venv/bin/python scripts/baseline_noskill.py EURUSD 1h` → the honesty check: model
   versus random direction.
4. Switch the dashboard to **Live** mode and send one paper order → shows the execution
   layer working end to end without a broker.

---

## 5. Limitations to state before they're asked

- Win rate is largely exit geometry; the model's edge shows in profit factor.
- 30–37 trades per pair; wide confidence intervals; one fixed split, ~4.8 months of
  out-of-sample data, no walk-forward validation.
- Sharpe is per-trade and below target on every configuration.
- Label and trades differ in three ways; aligned, the edge disappears.
- Volume is a futures proxy for spot activity.
- No live broker run: execution latency (<500 ms) and the report's Scenario C are untested.
- Backtests assume the stop was hit first when a candle touches both barriers — the
  conservative choice, but a candle hides what happened inside it.
