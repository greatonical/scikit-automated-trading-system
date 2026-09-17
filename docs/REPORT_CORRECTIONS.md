# Corrections for Chapters 1–3 of the Report

Factual mismatches between the report and what was actually built and measured. The
report file is **not** edited by this project — apply these in the Word version, in your
own words.

**Reviewed against the version dated 2026-09-17** ("DESIGN AND IMPLEMENTATION OF AN
AUTOMATED FINANCIAL TRADING SYSTEM FOR THE FOREIGN EXCHANGE MARKET"), now stored in the
repo as `GABRIEL_AWOSUSI_PROJECT_REPORT_CHAPTER_1-3.md` (it replaced the older
`…_corrected.md` copy). Sections are referenced by heading, not line number, because the
Word version paginates differently.

Priority: **A** = factually wrong and likely to be noticed; **B** = inconsistent with
the implementation; **C** = presentation / completeness.

---

## Already fixed since the earlier copy — no action needed

- **§3.4.1 Scikit-Learn** now describes the library correctly (Random Forest, no GPU,
  lighter image) instead of claiming it performs the rule-based filtering and Z-Score
  standardisation. *(Minor: the trailing clause "which scales to handle the deeper
  predictive price modelling" is vague — consider cutting it.)*
- **A References section now exists** (see C-15 for what's still missing from it).
- **§2.4** now lists five numbered research gaps rather than three plus two unnumbered.
- **§1.5** is no longer formatted as a heading.

---

## A — factually wrong

1. **Data span and test period** (§3.2.1, Table 3.1 caption, §3.4.2, §3.5, and §1.3).
   The report says five years of 1h/4h data (2019–2024), a test set of "approximately
   2019 to mid-2023" / "mid-2023 to 2024" / "2024 data", and a "three-month" testing
   period. Yahoo Finance serves only ~730 days of intraday data, so the system uses
   **1h data from mid-June 2024 to 12 June 2026**, with a held-out test set of
   **20 January – 12 June 2026 (~4.8 months, 2,456 hourly bars)**. The 80/20
   chronological split itself is exactly as described. → State the real window and the
   reason (Yahoo's intraday limit). This appears in at least five places; fix them all.

2. **Where the volume comes from** (§3.3.1, §3.2). The report never mentions that spot
   FX reports **zero volume** on Yahoo. Price comes from spot; volume comes from the
   matching **CME FX futures (6E=F, 6B=F)**, aligned by timestamp, as the standard
   proxy for institutional activity. → Add this; the entire volume gate rests on it.
   Also soften "proving institutional participation" to "indicating".

3. **What the rule-based filter actually is** (§2.2, final paragraph). The text says the
   rule layer "uses technical indicator signals as a precondition for trade execution",
   citing Chong et al. and Cardoso. The implemented filter is the **Volume Z-Score >
   +1.5** gate. RSI and MACD were tested as model *features* and **rejected** — they
   reduced win rate and profit factor on both pairs. → Reword, or say the literature
   motivated testing them and report that the test failed (a good result to own).

4. **"Order block" identification** (§1.8 definition, §2.4 gap 3, §2.5).
   **Updated 2026-09-17 — this is now partly true, and the honest version is better than
   deletion.** Order blocks *have* been implemented (break of structure confirmed by a
   close, ATR-filtered zone, consumed on mitigation) and given to the Random Forest as
   three features. Measured on both pairs, they improved only GBP/USD at the default
   exits and hurt the other three pair/config combinations, so they are **off by
   default** (`docs/RESULTS.md`, Step F).
   → Keep the concept in §1.8 and §2.4, and rewrite §2.5: the system does **not** trade
   order blocks as a rule layer — the rule layer is the volume-anomaly filter — but order
   blocks were implemented and tested as model features and rejected on the evidence.
   Report it in Chapter 4 as a measured negative result; it is stronger than a claim.

5. **Table 3.1.** The "Algorithmic Action" column triggers a BUY on a Close Z-Score of
   −2.45 and flags "Overbought"/"Reversion" on Close Z-Scores. The implemented system
   never acts on the Close Z-Score; it trades only when **Volume Z > 1.5 AND** the
   Random Forest is confident. The table also has no Volume Z-Score column, though the
   volume gate is the rule. → Replace with real rows (timestamp, OHLC, Volume,
   Z(Close), Z(Volume), P(win), action) from the actual dataset, or relabel the table
   as illustrating the Z-Score formula only.

6. **Live evaluation on an MT5 demo account** (Objective 4 in §1.3, repeated in the
   prose; §3.5.1; Table 3.2 Scenarios B and C). All evaluation was done by
   **backtesting on the held-out set with a simulated broker** (spread and slippage
   modelled). The live MT5 connection was never run by this project: MetaTrader's
   Python API cannot initialise under Wine/Docker (`docs/WINE_VERDICT.md`), and the
   native-Windows host was verified in a sibling deployment, not here. Scenario C's
   "stop-loss within 500 ms" and the execution-latency target are **not measured**.
   → Say so plainly in Chapter 3 (method) and Chapter 4 (limitations). See §D below
   for exactly what the sibling deployment does and does not support.

## B — inconsistent with the implementation

7. **The label is never defined.** The report says class 1 = "bullish continuation".
   The system uses the **triple-barrier label** (López de Prado, 2018): class 1 if the
   take-profit is hit before the stop-loss within 24 hours. → Define it in §3.4.2. It
   was the single most important design decision — it flipped both pairs from net loss
   to net profit.

8. **"Z-Score normalisation applied to all input features"** (§3.5 overfitting
   paragraph; also §3.2.2 "models cannot accurately process raw price data"). Only
   Close and Volume are Z-scored; raw Open/High/Low/Close/Volume are also inputs.

9. **"Training and validation sets"** (§1.4). The split is chronological train/test;
   hyperparameters are tuned with `TimeSeriesSplit` cross-validation **on the training
   set only**.

10. **Table 2.1, the two LSTM rows** (Hu, Zhao & Khushi; Yildirim et al.). "Supports use
    of LSTM for Forex price direction prediction" and "Closely aligned with proposed ML
    prediction layer" read as endorsements, but the design explicitly rejects deep
    learning. → e.g. "Reviewed; not adopted (compute cost, opacity)".

11. **Direct MT5 routing and "ultra-low latency"** (§1.4, §3.1, §3.4.1). The Python API
    is Windows-only, so the engine reaches MT5 through a small RPC service on a Windows
    host. No latency figure has been measured.

12. **Docker "ensuring 99.9% uptime"** (§3.4.1). Unsupported — soften to
    "restart-on-failure and reproducible environments".

13. **The 60% win-rate benchmark** (§1.3). Check that Barber & Odean (2000) and Dixon
    et al. (2020) actually state a 60% win-rate benchmark before citing them for it.
    If they don't, present 60% as the project's own stated target.

14. **Sharpe ratio convention** (§2.3, Table 3.3). The target "> 1.0" is conventionally
    annualised; the implementation reports a **per-trade, unannualised** figure
    (0.13 / 0.22). → State the convention wherever the number appears in Chapter 4.

## C — presentation / completeness

15. **Reference list gaps.** Four works are cited in the text but missing from the list:
    - **European Securities and Markets Authority (2018)** — §1.2
    - **Barber et al. (2020)** — §1.2 (distinct from Barber & Odean, 2000, which is listed)
    - **Bailey et al. (2014)** — §2.4, gap 5
    - **Lopez de Prado (2018)** — §3.4.2 (the basis of the labelling method — the most
      important of the four)

    Also check: the text and Table 2.1 cite **"Huang et al. (2019)"** but the list says
    **Huang, J., Chai, J., & Cho, S. (2020)** — pick one. Verify the FinRL author list
    (Liu et al., 2020) and the venue given for Zarattini & Stamatoudis (2022)
    ("Journal of Algorithmic Trading"); and Salehpour & Samadzamini (2023) has no
    volume/page numbers.

16. **Figures 3.1 (use case) and 3.2 (class diagram)** have captions and blank space but
    no images in the file I reviewed; only the cover logo and one diagram (inside §1.3)
    are embedded. Check the Word version. Consider updating the class diagram to include
    `RiskManager`, `Backtester` and the three `ExecutionHandler` implementations, since
    those exist in the code.

17. **Objectives listed twice** (§1.3: the numbered list, then the same four repeated in
    prose). Keep one.

18. **Table 2.1, last row** (Chong, Ng & Liew): "Limitations" and "Suitability" cells are
    empty. Cardoso (2019) is discussed in the text but has no row.

19. **§2.3 vs Table 3.3.** The metrics framework in §2.3 omits Profit Factor, which
    Table 3.3 then sets a target for.

20. **§1.9 chapter titles.** "Chapter 3: System Analysis and Design" vs the actual
    heading "Proposed System Design and Methodology".

---

## D — What the sibling deployment does and does not support

This matters for Chapters 4 and 5, because it is easy to overstate.

**It supports (deployment/architecture only):**
- MetaTrader 5's Python API **cannot** initialise under Wine on Linux (`-10005`), proven
  across three environments including native x86, and including a byte-for-byte clone of
  a public working reference.
- The **native-Windows** route works: `initialize()` succeeded first try and a real demo
  trade was placed (HFMarkets demo, the same broker family configured in this project).
- The same execution architecture used here — an abstract handler plus an RPC service —
  runs in production there, which is evidence the design is sound.

**It does NOT support any trading claim in this report:**
- That system contains **no machine learning whatsoever** (verified by a repo-wide search
  for scikit-learn, TensorFlow, PyTorch, NumPy, pandas: zero matches). It trades gold on
  hand-written MetaTrader rules.
- It has never run this project's Random Forest, volume gate, triple-barrier label,
  currency pairs or timeframe.
- Therefore it cannot validate the win rate, profit factor, drawdown, Sharpe, or the
  < 500 ms latency target. Those remain **backtested on held-out data with a simulated
  broker**, which is an honest and defensible basis — but it is not a live result.

**A defensible sentence:** *"The Linux/Wine deployment route was shown to be unworkable,
and the native-Windows route was verified end-to-end in a sibling production deployment
using the same execution architecture; the strategy results reported here are obtained by
backtesting on held-out data with modelled transaction costs."*

Note also the direction of transfer: the sibling project's own planning document cites
**this** repository's container and RPC code as its starting reference, and this project
then adopted its falsification of the Wine route. That two-way exchange is the accurate
account, and a stronger one than a single-direction claim.

---

For Chapter 4, the measured material — and the caveats that must accompany it
(confidence intervals, the no-skill baseline, label/trade alignment, per-trade Sharpe) —
is in `docs/RESULTS.md` and `docs/STRATEGY_CONFIGS.md`. Chapter 4 must not contradict
Chapters 1–3, so apply the A-items above first.
