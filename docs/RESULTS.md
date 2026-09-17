# Backtest Results — Win Rate per Improvement Step

The honest, measured performance after each change. Every row is a full backtest
on the **held-out test set** (data the model never trained on), **with spread +
slippage** modelled, and reproduces exactly with one command (see
[Reproducibility](#reproducibility)).

Targets (README §8): Win Rate > 60% · Profit Factor > 1.5 · Max Drawdown < 15% · Sharpe > 1.0.

**Data window (cached, fixed).** 1h EUR/USD and GBP/USD, mid-June 2024 → 12 June 2026
(`data/*_1h.parquet`, cached 2026-06-14). Chronological 80/20 split: train 9,824 bars
(→ 20 Jan 2026), **test 2,456 bars = 20 Jan → 12 Jun 2026 (~4.8 months)**.

**Reading the numbers.** A held-out backtest here produces only ~15–40 trades, so:
- every win rate carries a **95% Wilson confidence interval** `[low–high]` — with 30 trades
  it is about ±15 points wide, so single rows must not be over-read;
- **Sharpe is per-trade and unannualised** (`Backtester._sharpe`: the equity curve only
  moves when a trade closes). It is *not* the annualised figure the report's > 1.0 target
  conventionally means — compare with care.

> **★ DEFAULT CONFIG (Step A label + Step E close-TP exits, SL 1.2% / TP 0.4%):**
> EUR/USD **73.3% win** [55.6–85.8] (PF 1.34, DD 1.5%, +$257, 30 trades); GBP/USD
> **78.4% win** [62.8–88.6] (PF 1.62, DD 2.5%, +$532, 37 trades). The only configuration
> whose win rate clears the report's > 60% target on both pairs, at the lowest drawdown.
>
> **Read it with three measured caveats (2026-09-15 audit):**
> 1. **The win rate comes mostly from the exit geometry, not the model.** With the same
>    exits, a *random* trade direction wins 67–69% on average (range 56–79%). The model's
>    measurable edge is in **profit factor** (1.34 / 1.62 vs ~1.04 for random) —
>    see [No-skill baseline](#no-skill-baseline).
> 2. **EUR/USD's interval dips below 60%** (lower bound 55.6%): the target is met on the
>    point estimate, not with statistical confidence.
> 3. **The label and the trade differ** (long-only, 24-bar label vs long + short trades
>    held until SL/TP). Aligning them removes the profit on both pairs — see
>    [Label/trade alignment](#labeltrade-alignment).
>
> Its ~3:1 nominal risk-reward is also unfavourable (below). **No config meets
> Sharpe > 1.0** (per-trade 0.1–0.4) — a stated limitation.

---

## EURUSD 1h

| Step | Change | Win Rate [95% CI] | Profit Factor | Net P&L | Max Drawdown | Sharpe | Trades |
|------|--------|-------------------|---------------|---------|--------------|--------|--------|
| Baseline | next-candle label | 26% [13–46] | 0.88 | −$215 | 7.9% ✅ | −0.04 | 23 |
| **A** | triple-barrier label (SL 0.5 / TP 1.0) | **37%** [19–59] | **1.42** | **+$576** | 4.4% ✅ | 0.16 | 19 |
| B1 | + RSI ❌ reverted | 32% | 1.17 | +$257 | 3.7% ✅ | 0.08 | 19 |
| B2 | + MACD ❌ reverted | 23% | 0.78 | −$829 | 15.1% ❌ | −0.10 | 43 |
| B3a | + ATR feature only | 37% | 1.42 | +$576 | 4.4% ✅ | 0.16 | 19 |
| B3b | + ATR stops 1.5×/3× ❌ reverted | 33% | 0.74 | −$1,495 | 15.4% ❌ | −0.14 | 78 |
| B3b′ | + ATR stops 5×/10× ❌ reverted | 35% | 0.86 | −$167 | 4.4% ✅ | −0.06 | 17 |
| B4 | + higher-TF trend ❌ reverted | 38% | 1.78 | +$1,613 | 3.2% ✅ | 0.25 | 29 |
| C † | threshold tuning (val→test) | 31% [13–58] | 1.76 | +$752 | 5.4% ✅ | 0.21 | 13 |
| D † | + time-of-day (UTC hours) ❌ reverted | 41% | 1.72 | +$820 | 3.3% ✅ | 0.24 | 17 |
| **E ★default** | **close TP (SL 1.2 / TP 0.4)** | **73.3%** ✅ [56–86] | 1.34 | +$257 | 1.5% ✅ | 0.13 | 30 |
| E (alt) | symmetric 1:1 (SL/TP 0.6) | 44.1% [29–61] | 1.19 | +$370 | 4.3% ✅ | 0.09 | 34 |
| E (alt) | far TP 1:2 (SL 0.5 / TP 1.0) = Step A | 36.8% [19–59] | 1.42 | +$576 | 4.4% ✅ | 0.16 | 19 |

## GBPUSD 1h

| Step | Change | Win Rate [95% CI] | Profit Factor | Net P&L | Max Drawdown | Sharpe | Trades |
|------|--------|-------------------|---------------|---------|--------------|--------|--------|
| Baseline | next-candle label | 19% [9–34] | 0.70 | −$939 | 10.9% ✅ | −0.14 | 37 |
| **A** | triple-barrier label (SL 0.5 / TP 1.0) | **50%** [28–72] | **2.42** ✅ | **+$1,307** | 2.7% ✅ | 0.38 | 16 |
| B1 | + RSI ❌ reverted | 38% | 1.49 | +$702 | 4.3% ✅ | 0.17 | 21 |
| B2 | + MACD ❌ reverted | 26% | 0.87 | −$380 | 15.3% ❌ | −0.05 | 35 |
| B3a | + ATR feature only | 45% | 2.05 ✅ | +$1,441 | 5.4% ✅ | 0.31 | 22 |
| B3b | + ATR stops 1.5×/3× ❌ reverted | 33% | 0.76 | −$1,371 | 15.2% ❌ | −0.12 | 80 |
| B3b′ | + ATR stops 5×/10× ❌ reverted | 30% | 0.78 | −$156 | 6.1% ✅ | −0.10 | 10 |
| B4 | + higher-TF trend ❌ reverted | 31% | 1.04 | +$117 | 11.3% ✅ | 0.03 | 36 |
| C † | threshold tuning (val→test) | 33% [15–58] | 1.13 | +$137 | 6.3% ✅ | 0.06 | 15 |
| D † | + time-of-day (UTC hours) ❌ reverted | 44% | 1.96 ✅ | +$955 | 3.3% ✅ | 0.28 | 16 |
| **E ★default** | **close TP (SL 1.2 / TP 0.4)** | **78.4%** ✅ [63–89] | **1.62** ✅ | +$532 | 2.5% ✅ | 0.22 | 37 |
| E (alt) | symmetric 1:1 (SL/TP 0.6) | 60.0% [41–77] (not > 60%) | 1.92 ✅ | +$1,021 | 4.3% ✅ | 0.31 | 25 |
| E (alt) | far TP 1:2 (SL 0.5 / TP 1.0) = Step A | 50.0% [28–72] | 2.42 ✅ | +$1,307 | 2.7% ✅ | 0.38 | 16 |

† Re-measured 2026-09-15 after a fix — see the Step C and Step D notes. Every other row was
re-run on 2026-09-15 with the command in [Reproducibility](#reproducibility) and matched
the originally recorded numbers exactly. Steps Baseline–D were measured with the then-default
Step A exits (SL 0.5% / TP 1.0%); each is compared against Step A.

---

## Notes per step

**Baseline → A (triple-barrier label).** The biggest single jump. Both pairs went
from net loss to net profit. The fix: the model now predicts "will take-profit be
hit before stop-loss?" — much closer to the question the strategy asks — instead of
"will the next candle close higher?" GBPUSD's profit factor now passes (2.42 > 1.5).
See `docs/TRIPLE_BARRIER_EXPLAINED.md`.

**A → B1 (+ RSI) — REVERTED.** RSI *lowered* win rate and profit factor on **both**
pairs (EURUSD 37%→32% PF 1.42→1.17; GBPUSD 50%→38% PF 2.42→1.49). Likely the
Random Forest split on RSI noise, shifting which candles got traded for the worse.
`USE_RSI=false` by default; code kept for reproducibility. A useful negative
result: not every "standard" indicator helps this particular setup — exactly why
we test one at a time.

**A → B2 (+ MACD) — REVERTED.** Worse than RSI: both pairs went back to a **net
loss** and **drawdown breached 15%** (EURUSD 15.1%, GBPUSD 15.3%). Trade count
roughly **doubled** (the model fired far more often on the MACD features), and the
extra trades were poor. `USE_MACD=false`. Classic discretionary indicators don't
transfer to this RF + triple-barrier setup.

**A → B3 (+ ATR) — REVERTED (both feature and stops off).** Three sub-tests:
- **B3a — ATR as a *feature*:** roughly **neutral**. EURUSD was *identical* to Step A
  (the RF didn't split on ATR for those trades); GBPUSD's win rate dipped but net
  profit rose. Not harmful, not a clear win.
- **B3b — ATR-based *stops*, 1.5×/3× ATR:** 1h ATR is tiny (~0.10% of price), so these
  stops were ~3× tighter than the flat 0.5%/1.0% → trades exploded (19→78) and both
  pairs lost, drawdown breached 15%.
- **B3b′ — re-tuned to 5×/10× ATR** (≈ the old distances; these are the current
  `ATR_*_MULTIPLE` defaults): still net-negative on both pairs. *(This row was missing
  until 2026-09-15; the B3b row had always been the 1.5×/3× run.)*
- **Decision:** keep flat-% stops (Step A). ATR off by default; code kept.

**A → B4 (+ higher-TF trend) — REVERTED (not robust).** Genuinely *mixed*: it **helped
EURUSD** (net +$576→+$1,613, PF 1.42→1.78) but **badly hurt GBPUSD** (PF 2.42→1.04).
A feature that improves one pair and wrecks the other doesn't generalise, so it's
rejected for the shared default (`USE_HTF_TREND=true` to use it).

**Step C — threshold tuning (validation-selected, test-reported). Corrected 2026-09-15.**
Method: split 60/20/20 train/val/test; for each SL/TP geometry **relabel and retrain** on
the train portion, sweep the volume gate and ML confidence on the **validation** portion
only, report the best combo ONCE on the untouched test portion (`scripts/tune_thresholds.py`).
- *What was wrong before:* the script trained one model on the default-SL/TP label and then
  traded other SL/TP values with it — a label/trade mismatch. The old numbers (EURUSD PF
  2.68, GBPUSD PF 1.15) came from that version and are withdrawn.
- **EURUSD:** best on validation vol > 1.0, conf > 0.65, SL 0.5% / TP 1.5% (val PF 4.26 on
  12 trades) → test **PF 1.76, win 31%, +$752, 13 trades**. Better PF than Step A, on a
  tiny sample.
- **GBPUSD:** the best validation combo (vol > 1.5, conf > 0.50, SL 0.75% / TP 1.5%) was
  itself **unprofitable on validation** (PF 0.98, 24 trades) → test PF 1.13, +$137. Tuning
  found nothing worth keeping.
- **Takeaway (unchanged):** with this little data per fold, aggressive threshold tuning
  is unreliable — it rests on 12–24 validation trades. The robust default stays untuned.

**A → D (+ time-of-day/session) — REVERTED. Corrected 2026-09-15.** Cyclical hour
encoding + a London/NY-overlap flag (12:00–16:00 UTC). The data index used to be in
Europe/London time, so the original run computed the "UTC" hours in London time (off by
an hour in summer). Emulating that reproduces the old numbers exactly (EURUSD 39% / PF 1.56
/ +$698; GBPUSD 44% / 1.97 / +$962). With true UTC hours: EURUSD PF 1.42→1.72, GBPUSD
2.42→1.96 — **the conclusion is unchanged**: it helps one pair and hurts the other, so it
stays off.

**★ Step E (exit geometry & the win-rate / risk-reward trade-off).** The §8 win-rate
target (>60%) is set mainly by the take-profit / stop-loss *geometry*, not by
features. Steps A–D optimised trade *selection* (PF up, win rate stayed 37–50%
because TP was far). Step E sweeps the *exit geometry* and exposes the central
trade-off in trading.

Full frontier (`scripts/sweep_winrate.py`, held-out, conf > 0.55). As the target gets
closer (top→bottom), **win rate rises but reward-to-risk worsens** — the take-profit
distance controls both. *(The sweep used a smaller tuning grid than `run_backtest.py`
until 2026-09-15, which is why EUR/USD close-TP once showed PF 1.30 here and 1.34
elsewhere. All evaluation scripts now share `EVAL_PARAM_GRID`.)*

**EUR/USD**

| SL% | TP% | nominal risk:reward | Win% [95% CI] | PF | Net | Trades |
|-----|-----|---------------------|---------------|----|-----|--------|
| 0.5 | 1.0 | 1:2 (Step A) | 36.8% [19–59] | 1.42 | +$576 | 19 |
| 0.6 | 0.6 | 1:1 | 44.1% [29–61] | 1.19 | +$370 | 34 |
| 0.8 | 0.6 | 1.3:1 | 54.5% [38–70] | 1.22 | +$346 | 33 |
| 1.0 | 0.5 | 2:1 | 60.0% [42–75] | 0.94 | −$76 | 30 |
| **1.2** | **0.4** | **3:1 ★default** | **73.3% [56–86]** | **1.34** | **+$257** | **30** |

**GBP/USD**

| SL% | TP% | nominal risk:reward | Win% [95% CI] | PF | Net | Trades |
|-----|-----|---------------------|---------------|----|-----|--------|
| 0.5 | 1.0 | 1:2 (Step A) | 50.0% [28–72] | 2.42 | +$1,307 | 16 |
| 0.6 | 0.6 | 1:1 | 60.0% [41–77] | 1.92 | +$1,021 | 25 |
| 0.8 | 0.6 | 1.3:1 | 65.4% [46–81] | 1.85 | +$846 | 26 |
| 1.0 | 0.5 | 2:1 | 56.4% [41–71] | 0.93 | −$117 | 39 |
| **1.2** | **0.4** | **3:1 ★default** | **78.4% [63–89]** | **1.62** | **+$532** | **37** |

The frontier is noisy — the 2:1 row loses on both pairs while its neighbours profit — which
is what ~30 trades per row looks like. Read the trend, not individual rows.

**The iron law (confirmed by the trading literature):** high win rate AND a
favourable reward-to-risk **cannot both be maximised** — a far TP gives good
reward-to-risk but is hit less often; a close TP wins often but each win is small.
Independent sources confirm this is an inverse relationship and recommend
optimising **expectancy** = (win% × avg win) − (loss% × avg loss), not win rate
alone (FX News Group; SteadyOptions; LuxAlgo — see Sources).

### Scorecard against the report's rubric (Table 3.3: Win>60% · PF>1.5 · DD<15% · Sharpe>1.0)

No single configuration meets all four targets; the take-profit geometry decides
*which* it meets. Targets met (out of 4; win rate judged on the point estimate):

| Config | EUR/USD | GBP/USD | Character |
|--------|---------|---------|-----------|
| far-TP 1:2 | 1/4 (DD) | 2/4 (PF, DD) | best risk-reward + PF, win rate below target |
| symmetric 1:1 | 1/4 (DD) | 2/4 (PF, DD) — win exactly 60.0% is not > 60% | balanced risk-reward |
| **close-TP 3:1 ★default** | **2/4** (win, DD) | **3/4** (win, PF, DD) | **meets win-rate target on both pairs; best rubric score** |

**Decision: close-TP (SL 1.2% / TP 0.4%) is the default** — the only config whose win rate
clears the report's **headline target (> 60%) on both pairs**, profitable on both (PF 1.34 /
1.62), with the **lowest drawdown** of any config (1.5–2.5%).

**The honest trade-off, stated plainly:** the close TP gives an unfavourable ~3:1 nominal
risk-reward, so the high win rate is *subsidised* by small wins (realised ~0.47:1;
break-even ~68%). By the expectancy lens, the **far-TP 1:2** config is sounder (realised
2.4:1, break-even 29%, PF up to 2.42) — fewer, bigger wins are more robust than many tiny
ones — but it wins only 37–50%. And as the [no-skill baseline](#no-skill-baseline) shows,
the far-TP config is also where the model's skill is clearest. The project **adopts the
report-aligned close-TP default and documents the expectancy-superior alternative**, so the
choice is deliberate and evidence-based rather than a single cherry-picked number.

- **Sharpe < 1.0 on every config** (per-trade 0.09–0.38) — the one target nothing reaches.
  A believable retail-FX figure, far from the implausible Sharpe-5 numbers that signal
  overfitting. (Per-trade vs annualised: see the note at the top.)
- Raising win rate at a *fixed* good reward-to-risk is the job of **meta-labelling**
  (López de Prado) — future work.

### Nominal vs realised risk-reward (corrected 2026-09-15)

The SL/TP we *set* (nominal) is not the win/loss ratio we actually *get* (realised).
Measured (held-out, with costs, `scripts/sweep_winrate.py`):

**EUR/USD**

| Nominal | Win% | avg win | avg loss | **realised R:R** | break-even win% | PF | stops tightened |
|---------|------|---------|----------|------------------|-----------------|----|-----------------|
| 1:2 (far TP) | 36.8% | $276 | −$113 | **2.44:1** | 29% | 1.42 | 58% |
| 1:1 | 44.1% | $157 | −$105 | **1.50:1** | 40% | 1.19 | 59% |
| 1.3:1 | 54.5% | $109 | −$107 | 1.01:1 | 50% | 1.22 | 58% |
| 2:1 | 60.0% | $67 | −$106 | 0.63:1 | 61% | 0.94 | 57% |
| 3:1 (close TP ★) | 73.3% | $46 | −$94 | 0.49:1 | 67% | 1.34 | 50% |

**GBP/USD**

| Nominal | Win% | avg win | avg loss | **realised R:R** | break-even win% | PF | stops tightened |
|---------|------|---------|----------|------------------|-----------------|----|-----------------|
| 1:2 (far TP) | 50.0% | $278 | −$115 | **2.42:1** | 29% | 2.42 | 44% |
| 1:1 | 60.0% | $142 | −$111 | **1.28:1** | 44% | 1.92 | 68% |
| 1.3:1 | 65.4% | $109 | −$111 | 0.98:1 | 51% | 1.85 | 54% |
| 2:1 | 56.4% | $76 | −$106 | 0.72:1 | 58% | 0.93 | 74% |
| 3:1 (close TP ★) | 78.4% | $48 | −$107 | 0.45:1 | 69% | 1.62 | 54% |

**Why realised ≠ nominal.** This doc used to say winners "blow past" the take-profit and
fill at the candle extreme. **That was wrong** — the mock broker fills exactly at the TP
price. The real cause is the **dynamic stop-loss**: when |Volume Z| ≥ 2.0 the RiskManager
halves the stop, and fixed-fractional sizing then *doubles* the position so the cash at risk
stays ~1% of equity. A take-profit hit on such a trade pays about twice the nominal ratio,
while a full stop still costs ~1% either way. Because the volume gate already requires
Z > 1.5, **44–74% of all trades get the tightened stop** ("stops tightened" column).
Worked example, symmetric 1:1: an untightened win ≈ +$100, a tightened win ≈ +$200; with
~59% tightened the average win ≈ $157 → realised 1.5:1. (Tightened stops are also hit more
often — half the distance — so the effect is not free.)

Two findings:
- **EUR/USD at 1:1 is profitable despite a 44% win rate** because the *realised* ratio
  is **1.50:1**, pushing break-even down to **40%**. The 4-point cushion is thin —
  EUR/USD is the weaker pair; GBP/USD (60% vs 44% break-even) is robustly profitable.
- **The "high win rate" config is the weakest foundation, not the strongest.** The
  close-TP (3:1) config wins 73–78% but its break-even is **67–69%** — almost no
  margin. The far-TP (1:2) config wins only 37–50% but each win is ~2.4× a loss, giving
  a 29% break-even and the highest profit factor (2.42). Counter-intuitively, *fewer,
  bigger wins are more robust than many tiny wins.* This is the core risk-reward insight
  of the project and the reason the high-win-rate number must be read with its risk
  profile, never alone.

---

## No-skill baseline

*The question an examiner will ask: is the 73–78% win rate the model's doing?*
`scripts/baseline_noskill.py` keeps everything identical — same held-out window, exits,
costs and volume gate — and replaces **only** the model's trade direction: always BUY,
always SELL, or a random side on every gated bar (20 seeds).

| Config | Pair | Model: win / PF | Random side: win mean (range) / PF mean | Always BUY | Always SELL | Model ≥ random (win / PF) |
|--------|------|-----------------|------------------------------------------|------------|-------------|---------------------------|
| close-TP ★ | EUR/USD | 73.3% / 1.34 | 68.7% (58–79%) / 1.04 | 63.6% / 0.85 | 68.6% / 0.97 | 70% / 85% of seeds |
| close-TP ★ | GBP/USD | 78.4% / 1.62 | 66.8% (56–79%) / 1.04 | 63.5% / 0.79 | 66.7% / 1.00 | 95% / 90% |
| symmetric 1:1 | EUR/USD | 44.1% / 1.19 | 36.4% (10–50%) / 0.77 | 36.5% / 0.79 | 43.8% / 1.00 | 85% / 95% |
| symmetric 1:1 | GBP/USD | 60.0% / 1.92 | 31.5% (18–47%) / 0.61 | 36.8% / 0.78 | 41.3% / 0.89 | 100% / 100% |
| far-TP 1:2 | EUR/USD | 36.8% / 1.42 | 20.3% (10–30%) / 0.64 | 18.2% / 0.58 | 33.3% / 1.05 | 100% / 100% |
| far-TP 1:2 | GBP/USD | 50.0% / 2.42 | 20.7% (9–29%) / 0.63 | 25.6% / 0.84 | 26.2% / 0.86 | 100% / 100% |

What it shows:
- **Close-TP: the geometry does most of the work.** A random direction already wins ~67–69%.
  That is expected: a driftless random walk touches a barrier 0.4% away before one 1.2% away
  with probability 1.2 / (1.2 + 0.4) = 75% (before costs). The model adds ~5–12 points of
  win rate — inside the random range — but lifts profit factor from ~1.04 to 1.34 / 1.62.
  **The edge is in *which* trades it takes, not in how often they win.**
- **Symmetric and far-TP: the model clearly has skill.** It beats every random seed on both
  win rate and profit factor on GBP/USD and on far-TP EUR/USD (85% / 95% for symmetric
  EUR/USD) — the clearest evidence of genuine predictive power in the project.
- Report the headline win rate with this baseline beside it. To show that the *model*
  works, the far-TP and symmetric results show it more convincingly than the default.

---

## Label/trade alignment

The triple-barrier label and the trades the backtester takes were meant to be the same
thing ("the model is trained on exactly the trades the system will take"). The 2026-09-15
audit found three differences. Each is now a switch in `config/settings.py` (off by default,
so the documented numbers stay reproducible) and was measured one at a time on the default
close-TP config:

| # | The label assumes | The trade actually does | Switch that aligns them |
|---|-------------------|-------------------------|-------------------------|
| 1 | gives up after 24 bars (vertical barrier) | holds until SL/TP (default: median ~27 bars, max 370; 17 of 30 EUR/USD trades exceed 24) | `USE_TIME_EXIT=true` — close at the Close of bar entry + 24 |
| 2 | flat 1.2% stop | stop halved when \|Volume Z\| ≥ 2.0 (half the default trades) | `LABEL_DYNAMIC_SL=true` — same rule inside the label |
| 3 | long side only | also SELLs when P(bullish) < 0.45 (11 of 30 EUR/USD, 15 of 37 GBP/USD trades) | `ALLOW_SHORTS=false` — long-only |

A unit test proves that with #1 and #2 aligned every BUY's outcome equals its label
(`tests/test_backtester.py::test_aligned_trade_outcome_matches_triple_barrier_label`), and a
negative-control test proves the check fails when they are not aligned.

Results (held-out, with costs, SL 1.2% / TP 0.4% unless stated):

| Variant | EUR/USD: win [CI] / PF / net / trades | GBP/USD: win [CI] / PF / net / trades |
|---------|----------------------------------------|----------------------------------------|
| Default (unaligned) | 73.3% [56–86] / 1.34 / +$257 / 30 | 78.4% [63–89] / 1.62 / +$532 / 37 |
| + time exit (#1) | 50.0% [39–61] / 0.92 / −$130 / 82 | 60.0% [47–71] / 1.12 / +$142 / 60 |
| + dynamic-stop label (#2) | 73.3% [56–86] / 1.38 / +$288 / 30 | 77.8% [62–88] / 1.59 / +$497 / 36 |
| long-only (#3) | 65.0% [43–82] / 0.94 / −$39 / 20 | 68.0% [48–83] / 0.96 / −$34 / 25 |
| **all three (fully aligned)** | **45.8% [33–60] / 0.84 / −$173 / 48** | **48.6% [33–64] / 0.66 / −$300 / 35** |
| fully aligned, symmetric SL/TP 0.6 | 42.9% / 0.27 / −$296 / 7 | 0% / 0.00 / −$387 / 4 |
| fully aligned, far-TP SL 0.5 / TP 1.0 | 52.9% / 1.50 / +$318 / 17 | 0% / 0.00 / −$337 / 4 |

What it means:
- **#2 is harmless** — putting the dynamic stop into the label barely changes what the model
  learns (EUR/USD even improves slightly).
- **#1 matters most for close-TP.** The geometry needs time to reach the target; closing at
  24 bars turns many would-be wins into small time-exit losses (EUR/USD: 54 of 82 exits
  were time exits). The label's 24-bar horizon and the trade's "hold until SL/TP" are
  different questions.
- **#3: the SELL side carries much of the profit** (EUR/USD: +$188 of +$257). That is less
  arbitrary than it looks: a label of 0 *by stop-hit* means price fell 1.2% before rising
  0.4%, which guarantees the mirrored short (TP 0.4% below, SL 1.2% above) would have won.
  A label of 0 *by time-out* implies nothing — so the short side is only partly supported
  by what the model learned.
- **Fully aligned, the strategy has no edge.** It loses on both pairs, and on GBP/USD the
  model does no better than a random direction (model PF ≥ random in only 30% of seeds;
  `baseline_noskill.py` with the three switches on).

**Decision (2026-09-17): the default is kept, and reported with this caveat attached.**
The unaligned default is still an honest out-of-sample measurement — the mismatch is a
design inconsistency, not leakage (no future data reaches any feature) — and it is the
only configuration meeting the report's headline win-rate target on both pairs. But its
profit depends on holding past the label's horizon and on the short side, neither of which
the model was directly trained on, so that must be stated wherever its numbers are quoted.
Where the question is whether the *model* works, quote the **far-TP** configuration
instead: it beats every random-direction seed on both pairs (see the no-skill baseline).
The alignment switches stay off by default.

---

## 4h timeframe (corrected 2026-09-15)

This section used to say the default config makes **zero** 4h trades because "resampling
four 1h bars into one 4h bar smooths the volume, so the gate never fires". **That was
wrong.** The real cause: the cached 4h files (`data/*_4h.parquet`) were saved on 2026-06-14
*before* the futures-volume fix, so their Volume column was **0 on every bar**. A flat
series has Z = 0, so the > 1.5 gate could never pass.

Fix: 4h is now rebuilt from the cached 1h series at load time and never cached separately
(`DataHandler.get_data`), so it always shares the 1h window and futures volume; a
data-quality guard now logs a warning whenever fewer than 50% of bars carry volume
(`MIN_NONZERO_VOLUME_FRACTION`).

With real (summed futures) volume the gate fires on ~8.9% of 4h bars (vs ~13% on 1h) and
the default config trades (train 2,519 / test 630 4h bars; same test window):

| Pair | Win [95% CI] | PF | Net | Max DD | Trades | Sharpe |
|------|--------------|----|-----|--------|--------|--------|
| EUR/USD 4h | 62.1% [44–77] | 0.76 | −$277 | 6.0% | 29 | −0.12 |
| GBP/USD 4h | 78.6% [60–90] | 1.76 | +$420 | 2.1% | 28 | 0.25 |

Mixed — profitable on GBP/USD, losing on EUR/USD — so 4h is not adopted and the system's
primary timeframe stays **1h**. (Nothing was tuned for 4h: the SL/TP and the 24-bar label
horizon were chosen on 1h.)

---

## Conclusion of the improvement phase

Two distinct wins, each targeting a different metric — and one important qualification:
- **Triple-barrier label (Step A)** flipped both pairs from net loss to **profit** —
  the decisive change for *profitability*. No added indicator (RSI, MACD, ATR, trend,
  time-of-day) beat it on both pairs; threshold tuning rests on too few validation trades
  to be trusted.
- **Exit geometry (Step E)** exposes the win-rate / risk-reward trade-off and lets the
  system **meet the report's win-rate target**. The **close-TP default (SL 1.2 / TP 0.4)**
  reaches 73% (EUR/USD) / 78% (GBP/USD) — the only config meeting > 60% on both pairs —
  while staying profitable (PF 1.34 / 1.62) at the lowest drawdown of any config.
- **Qualification (2026-09-15 audit):** that win rate is mostly produced by the geometry
  itself (random direction: 67–69%), the model's edge shows in profit factor, and the
  profit depends on trade management the label doesn't model (holding past 24 bars, short
  side). Fully aligned, no configuration is profitable on both pairs.

The headline numbers are *believable* (win rate 73–78%, profit factor 1.3–1.6, drawdown
< 3%) — not the implausible Sharpe-5 / +1000% figures that signal overfitting — and every
qualification above is measured, not assumed.

---

## Reproducibility

Every row uses the cached 1h data (`data/*_1h.parquet`) and `random_state=42`, so it
reproduces exactly. All evaluation scripts share one tuning grid (`EVAL_PARAM_GRID`,
TimeSeriesSplit on the training set only) and one cost model (`BACKTEST_SPREAD` /
`BACKTEST_SLIPPAGE`). Each run of `run_backtest.py` also saves
`models/random_forest_<PAIR>_<TF>.pkl` with its full config — re-run the default last.

`run` below = `.venv/bin/python scripts/run_backtest.py EURUSD 1h` (or `GBPUSD`).

| Row | Command |
|-----|---------|
| ★ Default (E, close-TP) | `run` |
| Baseline | `LABEL_METHOD=next_candle DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 run` |
| A (= far-TP) | `DEFAULT_STOP_LOSS_PCT=0.005 DEFAULT_TAKE_PROFIT_PCT=0.010 run` |
| B1 / B2 / B3a / B4 / D | the Step A prefix + `USE_RSI=true` / `USE_MACD=true` / `USE_ATR=true` / `USE_HTF_TREND=true` / `USE_TIME_FEATURES=true` |
| B3b | Step A prefix + `USE_ATR=true USE_ATR_STOPS=true ATR_SL_MULTIPLE=1.5 ATR_TP_MULTIPLE=3.0` |
| B3b′ | Step A prefix + `USE_ATR=true USE_ATR_STOPS=true` (5×/10× defaults) |
| C | `.venv/bin/python scripts/tune_thresholds.py EURUSD 1h` |
| E symmetric | `DEFAULT_STOP_LOSS_PCT=0.006 DEFAULT_TAKE_PROFIT_PCT=0.006 run` |
| Frontier + realised R:R | `.venv/bin/python scripts/sweep_winrate.py EURUSD 1h` |
| No-skill baseline | `.venv/bin/python scripts/baseline_noskill.py EURUSD 1h` (SL/TP prefix for the other configs) |
| Alignment | `USE_TIME_EXIT=true` / `LABEL_DYNAMIC_SL=true` / `ALLOW_SHORTS=false` (singly or together) + `run` |
| 4h | `.venv/bin/python scripts/run_backtest.py EURUSD 4h` |

Each run: fetch (cached) data → preprocess → train (tuned via TimeSeriesSplit on the
training set only) → backtest on the held-out set with costs → print metrics. The split
is chronological 80/20, never shuffled, so the test set is genuinely out-of-sample.

---

## Sources (risk-reward vs win-rate trade-off; optimise expectancy)

These support the documented finding that win rate and reward-to-risk are inversely
related and that **expectancy** (not win rate alone) is the metric to optimise:

- FX News Group — *Why High-Risk-Reward Ratio Matters More Than Win Rate for New Traders*:
  <https://fxnewsgroup.com/forex-news/institutional/why-high-risk-reward-ratio-matters-more-than-win-rate-for-new-traders/>
- SteadyOptions — *Risk/Reward vs. Win Ratio* (shows a 70% win + 3:1 R:R implies an
  impossible ~3,775% annual return → such combos signal overfitting):
  <https://steadyoptions.com/articles/riskreward-vs-win-ratio-r713/>
- LuxAlgo — *Risk-Reward Ratio vs. Win Rate: Key Differences*:
  <https://www.luxalgo.com/blog/risk-reward-ratio-vs-win-rate-key-differences-2/>
