# Corrections for Chapters 1–3 of the Report

Factual mismatches between `GABRIEL_AWOSUSI_PROJECT_REPORT_CHAPTER_1-3_corrected.md`
and what was actually built and measured (found in the 2026-09-15 audit). The report
file itself has **not** been edited — apply these in the Word version, in your own
words. Line numbers refer to the `.md` copy in this repo.

Priority: **A** = factually wrong and likely to be noticed; **B** = inconsistent with
the implementation; **C** = presentation / completeness.

---

## A — factually wrong

1. **Data span and test period** (lines 204, 214, 270, 302; also §1.3 line 62).
   The report says five years of 1h/4h data (2019–2024), a test set of "mid-2023 to
   2024" / "2024 data", and a "three-month" test period. Yahoo Finance only serves
   ~730 days of intraday data, so the system uses **1h data from mid-June 2024 to
   12 June 2026**, and the held-out test set is **20 January – 12 June 2026 (~4.8
   months, 2,456 hourly bars)**. The 80/20 chronological split itself is as described.
   → State the real window and the reason (Yahoo's intraday limit).

2. **Where the volume comes from** (§3.3.1 line 230; §3.2 generally). The report
   never mentions that spot FX has no volume on Yahoo (it reports 0). The system takes
   price from spot and volume from **CME FX futures (6E=F, 6B=F)** as the institutional
   proxy. → Add this; it is the basis of the whole volume gate. Also soften "proving
   institutional participation" to "indicating".

3. **What the rule-based filter is** (§2.2 line 143). The text says the rule filter
   "uses technical indicator signals [MACD/RSI] as a precondition for trade execution".
   The implemented rule is the **Volume Z-Score > +1.5** gate; RSI and MACD were tested
   as model *features* and rejected (they hurt both pairs). → Reword, or say the
   literature motivated testing them.

4. **"Order block" identification** (§1.8 line 109; §2.4 item 3 line 182; §2.5 line
   190). The report describes "deterministic rule-based order block identification".
   Nothing in the system identifies order blocks; the rule layer is a volume-anomaly
   filter. → Remove or reframe as related work.

5. **Table 3.1** (lines 214–222). The "Algorithmic Action" column triggers a BUY on a
   Close Z-Score of −2.45 and flags "overbought"/"reversion" on Close Z-Scores. The
   implemented system never acts on the Close Z-Score; it trades only when **Volume
   Z > 1.5 AND** the Random Forest is confident. The table also has no Volume Z column.
   → Replace with real rows (timestamp, OHLC, Volume, Z(Close), Z(Volume), P(win),
   action) from the actual data, or label it clearly as illustrating the Z-Score
   formula only.

6. **Live evaluation on an MT5 demo account** (objective 4, lines 45 and 61; §3.5.1
   line 278; Table 3.2 Scenario B/C). All evaluation was done by **backtesting on the
   held-out set with a simulated broker** (spread + slippage modelled). The live MT5
   connection could not run under Wine/Docker (proven dead end — `docs/WINE_VERDICT.md`);
   it needs a native Windows host. Scenario C's "stop-loss within 500 ms" and the
   execution-latency target were not measured. → Say so plainly in Ch. 3 (method) and
   Ch. 4 (limitations).

## B — inconsistent with the implementation

7. **The label is never defined.** The report says class 1 = "bullish continuation".
   The system uses the **triple-barrier label** (López de Prado, 2018): class 1 if a
   take-profit is hit before the stop-loss within 24 hours. → Define it in §3.4.2; it
   was the single most important design decision (loss → profit on both pairs).

8. **"Z-Score normalisation applied to all input features"** (line 302; also §3.2.2
   line 208 "models cannot accurately process raw price data"). Only Close and Volume
   are Z-scored; raw Open/High/Low/Close/Volume are also model inputs. → Reword.

9. **Scikit-Learn's role** (§3.4.1 line 260). It says Scikit-Learn "manages the
   rule-based filtering and Z-Score standardisation". pandas/NumPy compute the
   Z-Scores and the rule is plain Python; Scikit-Learn provides the Random Forest,
   `TimeSeriesSplit` and `GridSearchCV`.

10. **"Training and validation sets"** (§1.4 line 72). The split is chronological
    train/test; hyperparameters are tuned with `TimeSeriesSplit` cross-validation on the
    training set only.

11. **Table 2.1, LSTM rows** (Hu, Zhao & Khushi; Yildirim et al., lines 158–159).
    "Supports use of LSTM for Forex price direction prediction" / "closely aligned with
    proposed ML prediction layer" reads as an endorsement, but the design explicitly
    rejects deep learning. → e.g. "Reviewed; not adopted (compute cost, opacity)".

12. **Direct MT5 routing** (§1.4 line 74, §3.1 line 196, §3.4.1 line 259). The Python
    API is Windows-only, so the engine talks to MT5 through a small RPC service on a
    Windows host (optional shared-secret token). "Ultra-low latency" is unmeasured.

13. **Docker "ensuring 99.9% uptime"** (§3.4.1 line 261). Unsupported — soften to
    "restart-on-failure and reproducible environments".

14. **The 60% win-rate benchmark source** (§1.3 line 62). Check that Barber & Odean
    (2000) and Dixon et al. (2020) actually state a 60% win-rate benchmark before citing
    them for it.

## C — presentation / completeness

15. **No References section** in this copy. In-text citations to list: Agrawal et al.
    (2013); Aldasoro et al. (2020); Bailey et al. (2014); Barber & Odean (2000); Barber
    et al. (2020); Cardoso (2019); Chong, Ng & Liew (2014); Cohen (2022); Dixon, Halperin
    & Bilokon (2020); ESMA (2018); Financial Stability Board (2019); Fischer (2018);
    Hayley & Marsh (2016); Henrique et al. (2019); Hu, Zhao & Khushi (2021); Huang et
    al. (2019); Liu et al. (2020); López de Prado (2018); Renani, Mohammadi & Moeeni
    (2013); Salehpour & Samadzamini (2023); Sezer et al. (2020); Sirignano & Cont
    (2019); Timmermann & Granger (2004); Yadav (2015); Yildirim, Toroslu & Fiore (2021);
    Zarattini & Stamatoudis (2022).
16. **Figures 3.1 (use case) and 3.2 (class diagram)** have captions but no images in
    this copy (only the cover logo and one diagram, placed inside §1.3, are embedded).
    Check the Word version. Consider updating the class diagram to include
    `RiskManager`, `Backtester` and the three `ExecutionHandler` implementations.
17. **Objectives listed twice** (§1.3: numbered list lines 42–45, then repeated in
    prose lines 47–61).
18. **Table 2.1 last row** (Chong, Ng & Liew, line 161): "Limitations" and "Suitability"
    cells are empty. Cardoso (2019) is discussed in the text but not in the table.
19. **§2.3 vs Table 3.3.** The metrics framework in §2.3 omits Profit Factor, which
    Table 3.3 then uses as a target.
20. **§1.9 chapter names.** "Chapter 3: System Analysis and Design" vs the actual
    heading "Proposed System Design and Methodology".

---

For Chapter 4, the measured material (and the caveats that should accompany it —
confidence intervals, the no-skill baseline, label/trade alignment, per-trade Sharpe)
is in `docs/RESULTS.md` and `docs/STRATEGY_CONFIGS.md`.
