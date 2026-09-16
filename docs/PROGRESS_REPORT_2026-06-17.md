# PROJECT PROGRESS REPORT

**Name:** Awosusi Gabriel Ayomide
**Reg. No:** CSC/2019/079
**Project Title:** Design and Implementation of an Automated Financial Trading System

---

### 1. What I Have Done So Far

**Literature Review (100%).** Completed and written up in Chapters 1 to 3. It covers the problem of retail trading losses, the case for a hybrid Z-Score plus Random Forest approach over deep learning, and the UML design (class, use-case and sequence diagrams).

**Methodology and Design (100%).** The modular architecture from Chapter 3 has been fully implemented. The analytical engine is kept separate from the execution layer, so data acquisition, preprocessing, the Random Forest model, the signal logic and risk management all run independently of MetaTrader 5.

**Implementation and Coding (about 90%).** The full Python system is built and runs end to end. It fetches EUR/USD and GBP/USD data from Yahoo Finance, computes rolling Z-Scores, trains a Scikit-Learn Random Forest using a chronological 80/20 split with TimeSeriesSplit cross-validation, and generates trades only when both the Volume Z-Score exceeds +1.5 and the model is confident. It also includes fixed-fractional position sizing, a backtesting engine and a Streamlit dashboard. As evidence, the codebase has 163 automated tests, all passing, across 15 modules. The remaining 10% is running the live MetaTrader 5 terminal inside Docker against a demo account.

**Analysis (about 85%).** I backtested the system on held-out data with spread and slippage included, using Scikit-Learn, pandas, NumPy and a custom backtester. The strongest result was that redefining the prediction target (a triple-barrier label that matches the actual stop-loss and take-profit exit) made both currency pairs profitable. GBP/USD reached a 50% win rate with a profit factor of 2.42 and 2.7% maximum drawdown, and EUR/USD a 37% win rate with a profit factor of 1.42. I also tested adding RSI, MACD, ATR and other indicators, and found that none of them improved results on both pairs, which is a useful finding in itself.

**Chapters Drafted.** Chapters 1 to 3 are final and I will send the current version by Friday 19 June. Chapter 4 (Implementation and Testing) has not been written yet, although the results and evidence it needs are already generated.

### 2. Most Difficult Aspects Remaining

1. Running the real MetaTrader 5 terminal headless under Wine in Docker and connecting it to a demo account. The code for this is built and tested against a simulated MetaTrader 5; the live broker connection is what remains.
2. Writing Chapter 4 and Chapter 5, bringing in the backtest results and the indicator analysis.

### 3. Current Challenges & Support Needed

The main technical challenge was that the MetaTrader 5 library only runs on Windows while I develop on macOS. I solved this in the design by depending on an abstract interface and putting the real terminal in a Wine and Docker container, so the only step left there is the live demo run.

On the results, the system is profitable on its best configuration and keeps drawdown well within the 15% target, but the win rate sits below the 60% benchmark. I intend to present this honestly in Chapter 4 with a full explanation of why, rather than overstate the performance. I would appreciate your confirmation that this framing is acceptable and any steers on how much detail you want in the results section.

### 4. Project Completion Plan

**Target date for final draft submission to supervisor:** Friday, 10 July 2026
**Target date for final project submission:** Friday, 24 July 2026

| Week | Dates | Focus |
|------|-------|-------|
| 1 | 17 to 23 Jun | Run the live MetaTrader 5 demo container, finalise results and figures, begin Chapter 4. |
| 2 | 24 to 30 Jun | Complete Chapter 4 with results, tables and screenshots. |
| 3 | 1 to 7 Jul | Write Chapter 5, and revise Chapters 1 to 3 based on your feedback. |
| 4 | 8 to 10 Jul | Combine everything into a full draft and submit it to you by 10 July. |

**Declaration:** I confirm that the above is a true reflection of my current progress.

**Name & Signature/Date:** Awosusi Gabriel Ayomide ______________ 17 June 2026
