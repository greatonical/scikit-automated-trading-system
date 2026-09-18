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

| # | Requirement | Current deck | Action |
|---|---|---|---|
| 1 | Introduction ≤ 2 slides | ✅ 2 slides | none |
| 2 | Literature review table: Author, Title, **Problem identified**, Methodology, **Solution proffered**, Remarks | ⚠️ columns are Method / Finding / Comment | restructure the table |
| 3 | Literature from the **last 2–3 years** (2023–2026) | ❌ 2000–2021 | add recent, verified papers |
| 4 | Gaps stated so they "sound like a problem" | ⚠️ implied, not listed | add an explicit gaps slide |
| 5 | Problem statement **after** the literature review, driven by the gaps | ❌ comes before | move and rewrite from the gaps |
| 6 | **One** aim that does not restate the title | ❌ restates the title | rewrite (proposal below) |
| 7 | **Exactly 5** objectives, Roman numerals, sequential, not "create/build", "formulate" for the model, last = evaluate | ❌ 4 objectives | rewrite (proposal below) |
| 8 | Methodology **for each objective**, naming the technology | ❌ one general slide | objective → method → tools table |
| 9 | Testing and evaluation slide | ❌ | add |
| 10 | Scope (direct, sharp) **then** justification | ❌ order reversed | swap |
| 11 | Work done, itemised: **Data collection and analysis**, design specification, implementation and prototype tools | ⚠️ no data slide | add a data collection and analysis slide |
| 12 | Diagrams labelled; figure label **below** | ✅ | none |
| 13 | Table label **above**, description **below** | ❌ tables unlabelled | label every table |
| 14 | Two screenshots per slide labelled Figure N and Figure N+1 (not 3a/3b) | ⚠️ slide 29 has one caption for two images | give each image its own number |
| 15 | System evaluation: usability criteria table + responses table | ❌ | depends on §1 |
| 16 | Explain the technical workings, not just sign-in/sign-up | ✅ strong | none |
| 17 | Conclusion **then** contribution to knowledge, then references | ❌ contribution comes before conclusion | reorder |
| 18 | Screenshots sharp, high resolution | ⚠️ slide 25 still placeholders | capture backtest output and dashboard |

"Work Left Undone" is a proposal-stage (503) heading; for the final defence consider
"Limitations and Future Work".

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
