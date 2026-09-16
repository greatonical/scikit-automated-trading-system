# The Triple-Barrier Label — Explained Simply

A plain-English guide to how we label the data, why it matters, and how the
stop-loss / take-profit prices are worked out. Come back here anytime.

---

## The problem it fixes

Before this change, the model was trained to answer one question:

> *"Will the next candle close higher?"*

But that is **not** how the strategy actually wins or loses. The strategy opens a
trade and then waits for one of two things: price hits the **take-profit** (win)
or the **stop-loss** (loss). That can take 1 candle or 50.

So there was a mismatch:
- The model learned to predict the **next candle**.
- The trade is decided by a stop/target **many candles later**.

A prediction can be "correct" (next candle up) and the trade **still loses**
(price dipped to the stop first). The model was studying for the wrong exam.

---

## What triple-barrier does

The moment a trade would open, we draw **three barriers** and label the candle by
**which barrier price touches first**:

```
        ┌──────────────── TAKE-PROFIT (upper) ──►  touched first = WIN  (label 1)
        │
  entry ●  · · · · · · · · · · · · · · · · · ·   (time runs to the right →)
        │
        └──────────────── STOP-LOSS (lower) ───►  touched first = LOSS (label 0)

        └── TIME LIMIT (vertical) ──► if neither is hit in N candles,
                                       label by where price ended up
```

The three barriers:
1. **Upper barrier** = the take-profit price.
2. **Lower barrier** = the stop-loss price.
3. **Vertical barrier** = a time limit (e.g. "give up after 24 candles").

For every candle in history we simulate: *"if I opened a trade here, which barrier
gets touched first?"* That answer becomes the label. Now the model learns the
**exact thing the strategy cares about**: *"from here, is take-profit reached
before stop-loss?"*

---

## Why it should lift the win rate

The model's "yes, trade" now means *"this setup historically hit profit before
loss."* That is directly aligned with how trades actually resolve.

This is why it's the highest-impact change: we are **not** giving the model more
clues (that's the RSI/MACD step). We are **fixing the question we ask it**.

---

## How TP / SL prices are calculated

The barriers are placed a set distance away from the entry price. Two ways to set
that distance (both live in `config/settings.py` — no magic numbers):

**1. Fixed percentage (the simple default)**
```
entry      = the candle's Close price
take-profit = entry × (1 + TP%)      # e.g. +1.0%  → 1.10 → 1.111
stop-loss   = entry × (1 − SL%)      # e.g. −0.5%  → 1.10 → 1.0945
```
(For a SELL it's mirrored: TP below, SL above.)

**2. Volatility-based with ATR (added in a later step)**
Instead of a flat %, the distance scales with recent volatility:
```
take-profit = entry + (ATR × TP_multiple)
stop-loss   = entry − (ATR × SL_multiple)
```
ATR ("Average True Range") measures how much price typically moves lately. In a
calm market the barriers sit closer; in a wild market, wider. This stops a flat %
from being too tight in storms or too loose in quiet periods.

**The important link:** the SL/TP used to **label** the data are the *same* SL/TP
the **RiskManager** uses to place real trades. Both read the same config values,
so labels and trades speak the same language — with three exceptions, below.

---

## The one rule that keeps it honest (no leakage)

- The **label** is allowed to look **forward** — that's the whole point; it's the
  answer ("did TP get hit before SL?").
- The **features** the model sees must stay **backward-looking only** (prices and
  indicators up to the current candle, never the future).

Label peeks at the future = correct. A *feature* peeking at the future = the bug
we always avoid (that's "data leakage" — see `docs/HOW_IT_WORKS.md`).

---

## Where the label and the real trade still differ (measured 2026-09-15)

The label describes a slightly different trade from the one the backtester takes.
None of this is leakage (no feature sees the future) — it's a mismatch between the
question the model answers and the trade that follows. Each difference has a switch
in `config/settings.py` (off by default so the documented numbers stay reproducible):

| The label… | …but the trade… | Switch |
|------------|-----------------|--------|
| gives up after 24 candles (vertical barrier) | is held until SL or TP, however long that takes | `USE_TIME_EXIT=true` |
| uses the flat stop distance | gets a stop *half* as far when \|Volume Z\| ≥ 2 (about half of trades) | `LABEL_DYNAMIC_SL=true` |
| only describes a **buy** | can also be a **sell** when the model is confident a buy would fail | `ALLOW_SHORTS=false` |

With the first two switched on, a unit test proves every buy's outcome equals its
label. Measured on the default config, aligning all three makes the strategy lose
money on both pairs — full numbers in `docs/RESULTS.md` "Label/trade alignment".

About the sell side: a label of 0 because the **stop was hit first** means price fell
far enough that the mirrored short would have won; a 0 from a **time-out** means
nothing either way. So selling on a low probability is partly, not fully, supported
by what the model learned.

---

## Source (for your viva)

This is the "triple-barrier method" from **Marcos López de Prado, *Advances in
Financial Machine Learning* (2018)** — already cited in your report (Chapter 3,
on the chronological split). So it's standard and defensible, not exotic.

---

## Quick glossary

- **Barrier** = a price level (or time limit) that ends the trade.
- **Take-profit (TP)** = the price where a winning trade auto-closes.
- **Stop-loss (SL)** = the price where a losing trade auto-closes.
- **Vertical barrier** = a maximum holding time.
- **ATR** = a measure of recent volatility, used to size the barriers.
- **Label** = the "right answer" the model is trained to predict (1 = win, 0 = loss).
