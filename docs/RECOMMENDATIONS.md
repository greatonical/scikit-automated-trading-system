# Recommendations & Things to Know

Honest notes on the system's limits and how to improve it. Useful for the viva and
for future work. Kept short on purpose. (Updated 2026-09-15 after the full audit.)

---

## 1. Weaknesses (know these, name them in your defence)

| Weakness | Why it matters |
|----------|----------------|
| **The headline win rate is mostly exit geometry** | With SL 1.2% / TP 0.4%, a *random* trade direction already wins ~67–69%. The model's measurable edge is in profit factor (1.34 / 1.62 vs ~1.04), not win rate. Quote the no-skill baseline next to the 73–78%. |
| **Small samples** | 30–37 trades per pair on the held-out set. EUR/USD's 73.3% has a 95% interval of 56–86% — its lower end is below the 60% target. |
| **Label ≠ trade** | The label is long-only with a 24-bar horizon; trades are long + short and held until SL/TP. Fully aligned, the strategy loses on both pairs (docs/RESULTS.md). |
| **Volume is a proxy** | We gate on CME futures volume (`6E=F`/`6B=F`) but trade spot. Futures activity *usually* tracks spot, not always. Spot FX has no native volume, so this is the best free signal — a constraint, not a flaw. |
| **One fixed split, one short test window** | ~4.8 months of test data (Jan–Jun 2026), a single chronological split, no walk-forward. Results may not hold in a different regime. |
| **Backtest ≠ live** | A backtest can't see real spread variation, slippage, or what price did *inside* an hourly candle. Real results will be worse. No live MT5 run exists yet. |
| **Intraday history ~2 years** | Yahoo caps 1h data at ~730 days, not the full 2019–2024. |

---

## 2. What reduces our edge (the costs)

- **Spread** — the broker's buy/sell price gap, paid on *every* trade. On a thin edge, this hurts most.
- **Slippage** — you don't always get the price you asked for.
- **Intra-candle moves** — within one 1h candle, price may hit your stop, then recover. The candle hides this (we assume the stop was hit first when both are touched — the conservative choice).

---

## 3. What can improve the system

**Done (measured in docs/RESULTS.md):**
- Risk management, the volume gate, spread/slippage modelling.
- Triple-barrier label (the decisive profitability fix).
- RSI, MACD, ATR, higher-timeframe trend, time-of-day, order blocks — tested one at a
  time, none improved both pairs.
- Validation-selected threshold tuning — too few validation trades to trust.
- Exit-geometry frontier, no-skill baseline, label/trade-alignment experiments.

**Future work (beyond this project's scope):**
- **Align the label with the trade properly**: a two-model design (one long-side and
  one short-side triple-barrier classifier), or a label whose horizon matches how
  trades are actually managed.
- **Meta-labelling** (López de Prado): a second model that decides *whether* to take
  a primary signal — the standard way to raise precision at a fixed risk-reward.
- **Walk-forward validation** (retrain periodically, test on each next window) for more
  than one out-of-sample period and more trades.
- **Annualised Sharpe** from daily mark-to-market equity, so the > 1.0 target is
  compared like-for-like.
- **Live measurement on Windows**: execution latency (< 500 ms target) and Scenario C.
- A true FX-volume data source (paid feed) instead of the futures proxy.
- More pairs / timeframes for robustness.

---

## 4. Viewing the saved models (`.pkl`)

- Each `scripts/run_backtest.py` run saves `models/random_forest_<PAIR>_<TF>.pkl`, with
  provenance (pair, data window, label/exit config, date trained). It is **not
  compiled** — `joblib.dump()` writes the in-memory model to disk as binary;
  `joblib.load()` reads it back.
- **Don't use a "PKL Viewer" extension** — joblib uses pickle protocol 5 with numpy
  arrays, which those extensions can't parse ("stack not empty" error).
- **To view them:** `.venv/bin/python scripts/inspect_model.py` — prints settings,
  provenance and feature importances for every model in `models/`.

---

## 5. The honest go/no-go

The real question — *"does this work for live trading?"* — is answered by the
**Backtester**, not by opinion. Run the full strategy on the held-out test data
**with spread/slippage included** and check the README §8 targets:

| Metric | Target |
|--------|--------|
| Win Rate | > 60% |
| Max Drawdown | < 15% |
| Profit Factor | > 1.5 |
| Sharpe Ratio | > 1.0 |

…and then check the result against a **no-skill baseline** (`scripts/baseline_noskill.py`):
a target met by random entries too says little about the model.

If it clears these *after costs* and beats the baseline → evidence it's tradeable.
If it doesn't → **that is a valid, reportable result.** The project is to design,
build, and *evaluate*. An honest negative with analysis beats a suspiciously
perfect one (which usually means a bug/leakage).
