# Chapter 4 — evidence pack: figure slots, captions, and how to produce each one

Paste-ready scaffold for "Implementation and Testing". Each slot says **what to capture**,
gives a **caption**, and names the **command that produced it** — put that command in the
caption, because a screenshot proves the system runs while the command proves the number.

Numbering assumes Chapter 4 follows the section order below; renumber freely.
Figures: 13 · Listings: 5 · Tables: 5.

---

## 4.1 Implementation overview

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.1 — system architecture diagram ]               │
│                                                              │
│   Draw: Yahoo Finance → DataHandler → Preprocessor →         │
│   MLModel → SignalGenerator → RiskManager → ExecutionHandler │
│   (Mock | MT5 | RemoteMT5), with the Streamlit dashboard     │
│   alongside and Docker around the engine.                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.1:** Module architecture of the implemented system. The execution layer sits
behind one abstract interface, so the analytical engine never depends on MetaTrader 5.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.2 — repository structure ]                      │
│                                                              │
│   Capture: your IDE's file tree, or `tree -L 2 -I '.venv'`   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.2:** Repository layout. Source: `github.com/greatonical/scikit-automated-trading-system`

---

## 4.2 Data acquisition and preparation

**Table 4.1 — dataset summary.** Fill from the run header of `run_backtest.py`:

| Property | EUR/USD | GBP/USD |
|---|---|---|
| Source | Yahoo Finance (spot) + CME futures volume | same |
| Interval | 1 hour | 1 hour |
| Coverage | mid-June 2024 → 12 June 2026 | same |
| Bars (train / test) | 9,824 / 2,456 | 9,824 / 2,457 |
| Test window | 20 Jan – 12 Jun 2026 | same |
| Split | chronological 80/20, never shuffled | same |

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.3 — terminal: data load and split ]             │
│                                                              │
│   Capture: the first lines of a run —                        │
│   "config: label_method=… " and                              │
│   "train=9824 test=2456 (2026-01-20 -> 2026-06-12)"          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.3:** Chronological split of the held-out evaluation period.
Produced by: `.venv/bin/python scripts/run_backtest.py EURUSD 1h`

> Say here why the window is ~2 years and not 2019–2024: Yahoo serves intraday data for
> roughly 730 days. And why volume comes from CME futures: spot FX reports zero volume.

---

## 4.3 Testing

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.4 — test suite passing ]                        │
│                                                              │
│   Capture: terminal showing "218 passed, 2 deselected"       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.4:** Automated test suite. Produced by: `.venv/bin/python -m pytest -q`

**Listing 4.1 — an anti-leakage test.** Paste
`tests/test_preprocessor.py::test_zscore_is_strictly_trailing_no_lookahead`. It deletes
future rows and asserts a past feature value is unchanged — the direct evidence that no
feature sees the future.

**Listing 4.2 — label/trade agreement.** Paste
`tests/test_backtester.py::test_aligned_trade_outcome_matches_triple_barrier_label`, and
mention its negative control, which proves the check can fail.

---

## 4.4 Method: how a trade is decided

**Listing 4.3 — the hybrid gate.** Paste `SignalGenerator.decide` from
`src/signal_generator.py` (the `rule_pass` / `bullish_pass` / `bearish_pass` block).
Note the strict `>`: exactly 1.5 or exactly 0.55 does not pass.

**Listing 4.4 — the triple-barrier label.** Paste the forward loop from
`Preprocessor.add_triple_barrier_labels` in `src/preprocessor.py`. This is the single most
important design decision in the project and the report has never defined it.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.5 — triple-barrier diagram ]                    │
│                                                              │
│   Draw: entry, upper barrier (take-profit), lower barrier    │
│   (stop-loss), vertical barrier (24 bars). The ASCII sketch  │
│   in docs/TRIPLE_BARRIER_EXPLAINED.md is the layout.         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.5:** The triple-barrier labelling scheme (López de Prado, 2018).

---

## 4.5 Results on the held-out set

**Table 4.2 — headline performance** (with costs; win rate with 95% Wilson interval):

| Metric | Target | EUR/USD | GBP/USD |
|---|---|---|---|
| Win rate | > 60% | 73.3% ✅ [55.6–85.8] | 78.4% ✅ [62.8–88.6] |
| Profit factor | > 1.5 | 1.34 ❌ | 1.62 ✅ |
| Max drawdown | < 15% | 1.5% ✅ | 2.5% ✅ |
| Sharpe (per-trade) | > 1.0 | 0.13 ❌ | 0.22 ❌ |
| Trades / net P&L | — | 30 / +$257 | 37 / +$532 |

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.6 — dashboard metrics row ]                     │
│                                                              │
│   Capture: the five metric cards + "Targets met: 2/4" +      │
│   the confidence-interval caption, after Run Backtest        │
│   (EURUSD, 1h, sliders at defaults)                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.6:** Evaluation results as presented by the dashboard, EUR/USD 1h.
Produced by: `.venv/bin/python -m streamlit run dashboard/app.py` → **Run Backtest**

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.7 — equity curve ]                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.7:** Account equity across the held-out period, EUR/USD 1h.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.8 — trade table ]                               │
│                                                              │
│   Capture: enough rows to show entry/exit times, exit        │
│   reasons (take_profit / stop_loss / end_of_data) and P&L    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.8:** Individual trades with exit reasons — evidence the backtester resolves
each trade bar by bar rather than computing a summary statistic.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.9 — feature importances ]                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.9:** Random Forest feature importances — the interpretability that motivated
choosing an ensemble over a neural network (§3.4.1).

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.10 — GBP/USD results ]                          │
│                                                              │
│   Capture: same dashboard view with Pair = GBPUSD            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.10:** Held-out results for the second pair, GBP/USD 1h.

---

## 4.6 The improvement phase

**Table 4.3 — cause and effect.** Copy the EUR/USD and GBP/USD tables from
`docs/RESULTS.md`: baseline → triple-barrier label → each rejected indicator → threshold
tuning → exit geometry. Keep the ❌ rows: measured negative results are evidence of method.

---

## 4.7 Honest analysis (the section that distinguishes the report)

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.11 — no-skill baseline ]                        │
│                                                              │
│   Capture: the terminal block showing model vs always-BUY    │
│   vs always-SELL vs random direction × 20 seeds              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.11:** Model versus no-skill baselines under identical exits. Random trade
direction already wins 68.7%, which is why the win rate must be read with this figure
beside it. Produced by: `.venv/bin/python scripts/baseline_noskill.py EURUSD 1h`

**Table 4.4 — exit-geometry frontier.** From `docs/RESULTS.md` Step E: as the target moves
closer, win rate rises and reward-to-risk falls. Produced by `scripts/sweep_winrate.py`.

**Table 4.5 — label/trade alignment.** From `docs/RESULTS.md`: the default, each switch
alone, and all three together. State plainly that fully aligned, the strategy loses on
both pairs.

---

## 4.8 Deployment

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.12 — containerised engine ]                     │
│                                                              │
│   Capture: `docker compose up engine` running, and the       │
│   dashboard served at localhost:8501 from the container      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.12:** The engine running under Docker (Objective 4's containerisation).

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.13 — execution path, paper mode ]               │
│                                                              │
│   Capture: dashboard Live tab → handler `mock` → the filled  │
│   order result showing volume 10000.0 and latency_ms         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.13:** The execution layer placing an order end to end without a broker. The
0.1 lots entered becomes 10,000 units — the engine's sizing unit — and the MT5 handler
converts back to broker lots.

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   [ FIGURE 4.14 — OPTIONAL: MT5 on native Windows ]          │
│                                                              │
│   Only if you include the deployment evidence.               │
│   REDACT: account numbers, balances, server names, tokens.   │
│   Show: the terminal running and initialize() succeeding.    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```
**Figure 4.14 (optional):** MetaTrader 5 running on a native Windows host, the deployment
route adopted after the Linux/Wine route was shown unworkable. Caption it as an
industrial application; it supports the deployment claim only, not any trading result.

**Listing 4.5 — units to lots.** Paste `MT5ExecutionHandler._units_to_lots` from
`src/execution/mt5.py`: it rounds **down** and rejects anything below the broker minimum,
so a live order can never exceed the risk the RiskManager sized for.

---

## Appendix

- **A.1 — Repository.** `github.com/greatonical/scikit-automated-trading-system`. State
  the commit hash you submitted against, so the examiner sees the exact code.
- **A.2 — How to reproduce every number.** Copy the Reproducibility table from
  `docs/RESULTS.md`: one command per row.
- **A.3 — Selected source listings.** Longer excerpts that don't fit inline.

---

### Capture checklist

- [ ] `pytest -q` → 218 passed (Fig 4.4)
- [ ] `run_backtest.py EURUSD 1h` full output (Figs 4.3, and the numbers for Table 4.2)
- [ ] `run_backtest.py GBPUSD 1h` full output (Fig 4.10 data)
- [ ] `baseline_noskill.py EURUSD 1h` (Fig 4.11 — the most important one)
- [ ] `sweep_winrate.py EURUSD 1h` (Table 4.4)
- [ ] Dashboard: metrics, equity curve, trades, importances (Figs 4.6–4.9)
- [ ] Dashboard Live tab, paper order result (Fig 4.13)
- [ ] `docker compose up engine` (Fig 4.12)
- [ ] Optional, redacted: Windows MT5 (Fig 4.14)

Screenshot tips: use a light terminal theme and a font size that survives printing; crop
to the relevant block; keep the command visible at the top of the capture so the figure
is self-evidencing.
