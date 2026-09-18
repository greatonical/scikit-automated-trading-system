# Supervisor's Notes: Requirements Checklist

Source: "Notes for Chapters.pdf" (supervisor, received 2026-09-18). Each requirement is
mapped to where the report and `docs/DEFENCE_PRESENTATION.pptx` stand today.
✅ met · ⚠️ partly · ❌ missing.

---

## 1. The single biggest gap: user evaluation (≥ 50 users)

> "Chapter 4 should contain feedback and analysis from user and statistical analysis …
> Minimum of 50 users … System evaluation … a table that shows different usability
> criteria, another table that shows the response."

**Status ❌.** The project has thorough *statistical* evaluation (held-out backtest,
Wilson confidence intervals, no-skill baseline) but **no user evaluation at all**.
This cannot be written, simulated or estimated. It has to be run.

Recommended design (standard, defensible, fast to analyse):

- **Instrument:** the System Usability Scale (SUS; Brooke, 1996): 10 fixed items on a
  5-point Likert scale, giving a 0–100 score (68 = industry average). Add 4–6
  system-specific items (clarity of the BUY/SELL/HOLD explanation, trust in the
  two-gate rule, usefulness of the risk limits, readability of the metrics) plus two
  profile questions (trading experience, broker used).
- **Respondents:** at least 50. Natural pool: the Gadel waiting list (real traders,
  already engaged), Computer Science classmates, and trading communities.
- **Access:** respondents must actually use the dashboard, either through a hosted
  link (e.g. Streamlit Community Cloud) or a guided walkthrough video. A hosted link
  is the stronger evidence.
- **Analysis:** per-item mean, standard deviation and % agreement; overall SUS score
  with a confidence interval; Cronbach's alpha for questionnaire reliability; a
  breakdown by experience level.
- **Report it as:** Table 4.x "Usability evaluation criteria" (the items) and
  Table 4.y "Summary of respondents' responses", as the supervisor describes.

**Never** fill these tables with invented responses. If fewer than 50 respond, report
the real number and state it as a limitation.

---

## 2. Presentation (the supervisor's order)

Status after the 2026-09-18 restructure (the deck is now 41 slides, local only):

| # | Requirement | Status |
|---|---|---|
| 1 | Introduction ≤ 2 slides | ✅ 2 slides |
| 2 | Literature table: Author, Title, Problem identified, Methodology, Solution proffered, Remarks | ✅ exactly these columns, over three slides |
| 3 | Literature from the last 2–3 years | ✅ 8 papers, 2023–2025, each confirmed in the Crossref DOI registry |
| 4 | Gaps stated so they sound like problems | ✅ new *Research Gaps* slide, each gap cited |
| 5 | Problem statement after the review, driven by the gaps | ✅ moved and rewritten from the gaps |
| 6 | One aim that does not restate the title | ✅ |
| 7 | Exactly 5 objectives, Roman numerals, sequential, "formulate", last = evaluate | ✅ (§4 below) |
| 8 | Methodology for each objective, naming the technology | ✅ objective → method → technology table |
| 9 | Testing and evaluation slide | ✅ |
| 10 | Scope then justification | ✅ |
| 11 | Work done itemised, with data collection and analysis | ✅ incl. a data slide computed from the real dataset |
| 12 | Diagrams labelled, figure label below | ✅ Figures 1–14, every image its own number |
| 13 | Table label above, description below | ✅ Tables 1–11 |
| 14 | Two screenshots per slide as Figure N and N+1 | ✅ |
| 15 | Usability criteria table + responses table | ⚠️ both tables built; responses **pending the real study** (§1) |
| 16 | Explain the technical workings | ✅ |
| 17 | Conclusion, then contribution to knowledge, then references | ✅ ("Work Left Undone" became "Limitations and Future Work") |
| 18 | Sharp, high-resolution screenshots | ⚠️ the *Prototype: Backtest Run and Dashboard* slide still has two placeholders |

**Open items for the author before the defence:**

- Run the usability study (`docs/USABILITY_STUDY.md`) and fill Table 11's "pending" cells.
- Capture the two prototype screenshots (backtest terminal output, dashboard).
- Open each literature DOI once in a browser. Arian et al. (2024) was verified in the
  DOI registry, but its abstract came from an SSRN listing rather than the publisher.
- Check the López-Herrera et al. (2025) co-author names against the published PDF:
  the DOI registry splits the Spanish surnames as "Jiménez, J.G.M." and "Santiago, A.R.".

---

## 3. Report chapters

**Chapter 1:** past tense throughout ("was developed", not "will be developed").
Exactly the same 5 objectives as the slides.

**Chapter 3:** all methodology lives here, organised per objective, with every
diagram (context, architecture, block, use case, activity, class) and **the reason
each diagram type was chosen**.

**Chapter 4** (must open with an *Overview*, not an Introduction; no methodology, no
repeated tools or libraries):

- 4.1 Overview
- 4.2 Prototype and prototype tools: a chronological screenshot walkthrough, each
  figure called out in the text ("as shown in Figure 4.1, the dashboard allows…"),
  arranged as if demonstrating the system live
- 4.3 System testing and evaluation: unit testing (231 automated tests, including
  anti-leakage tests), performance evaluation (backtest), usability evaluation (§1)
- 4.4 Results: backtest tables with confidence intervals, the no-skill baseline, the
  six negative results, usability results
- 4.5 Discussion: interpretation, including the analytical settings (thresholds,
  costs, split) and the statistics used

**Chapter 5:** conclusion, then contribution to knowledge, then references.

**Formatting:** justified text, double spacing, table labels above, figure labels
below, high-resolution figures, figures numbered consecutively.

---

## 4. Proposed aim and objectives (for the author to approve)

**Aim** (restates the problem, not the title): to reduce emotion-driven and
unverifiable decision-making in retail foreign-exchange trading through an automated,
explainable and honestly evaluated trading decision system.

**Objectives:**

i. To acquire and pre-process historical EUR/USD and GBP/USD market data, and derive
   trailing statistical features from price and exchange-traded futures volume.

ii. To formulate a hybrid predictive model in which a volume Z-Score filter and a
    Random Forest classifier, trained on triple-barrier labels, must jointly agree
    before a trade is taken.

iii. To design the architecture of the trading system, including its risk-management
     and broker-execution layers, using UML.

iv. To implement the designed system as a working prototype with a monitoring
    dashboard and a demo-account execution path.

v. To evaluate the system's trading performance on held-out data and its usability
   with prospective users.

| Objective | Method | Technology |
|---|---|---|
| i | Market data acquisition, cleaning, futures-volume merge, chronological 80/20 split | Python, pandas, NumPy, Yahoo Finance API |
| ii | Triple-barrier labelling, Random Forest, TimeSeriesSplit cross-validation | scikit-learn |
| iii | Context, use case, activity and class diagrams; layered architecture | UML |
| iv | Modular implementation behind an abstract execution interface | Streamlit, Docker, MetaTrader 5 API |
| v | Event-driven backtest with transaction costs, Wilson intervals, no-skill baseline; SUS questionnaire (n ≥ 50) | pytest, Google Forms, statistical analysis |
