# Report Update: Chapters 1 and 2 (to match the defence slides)

Ready-to-paste text for the Word report, in the report's APA style. It brings the report
in line with `docs/DEFENCE_PRESENTATION_27.pptx`: the recent literature (2023–2025), the
research gaps, the problem statement, and the aim and five objectives.

The report file itself is not edited here. Paste each part where it says.

---

## Part A: Chapter 1, §1.3 Aim and Objectives

Replace the whole of §1.3 (the numbered list *and* the repeated prose version) with:

> **Aim:** This project aimed to reduce emotion-driven and unverifiable decision-making in
> retail foreign exchange trading through an automated, explainable and honestly
> evaluated trading decision system.
>
> **Objectives:** The specific objectives of this project were to:
>
> i. acquire and pre-process historical EUR/USD and GBP/USD market data, and derive
>    trailing statistical features from price and exchange-traded futures volume;
>
> ii. formulate a hybrid predictive model in which a volume Z-Score filter and a Random
>     Forest classifier, trained on triple-barrier labels, must jointly agree before a
>     trade is taken;
>
> iii. design the architecture of the trading system, including its risk-management and
>      broker-execution layers, using UML;
>
> iv. implement the designed system as a working prototype with a monitoring dashboard
>     and a demo-account execution path; and
>
> v. evaluate the system's trading performance on held-out data and its usability with
>    prospective users.

---

## Part B: Chapter 1, §1.2 Problem Statement

Add this as the closing paragraph of §1.2, so the problem is driven by the literature:

> Retail foreign exchange traders lose money largely through emotional and inconsistent
> decisions (European Securities and Markets Authority, 2018), and the automated tools
> meant to help them are difficult to trust. Recent studies show that machine-learning
> trading performance is specific to each currency pair, collapses on unseen data and
> disappears once realistic costs are charged (Deep et al., 2025; Enkhbayar & Ślepaczuk,
> 2025; López-Herrera et al., 2025). The validation methods commonly used still allow
> backtest overfitting (Arian et al., 2024), and exchange-traded volume, the most direct
> measure of institutional activity, is not used to filter trades (Jongadsayakul, 2024).
> There is therefore no transparent, cost-aware and properly validated trading decision
> system for retail foreign exchange traders that combines a volume-based rule with
> machine learning.

---

## Part C: Chapter 2, new §2.2.2 Recent Studies (2023–2025)

Insert after Table 2.1 and before §2.2.1 (renumber the risk-management subsection to
§2.2.3 if you prefer the recent studies to come first):

> **2.2.2 Recent Studies (2023–2025)**
>
> More recent work has tested machine-learning trading systems under stricter and more
> realistic conditions, and much of it qualifies the optimism of earlier studies.
> López-Herrera et al. (2025) compared seven machine-learning models, including Random
> Forest and XGBoost, for directional forecasting on eight currency pairs against the US
> dollar between 2018 and 2023, using time-series cross-validation and spread-based
> transaction costs. Simpler models produced the best risk-adjusted returns, and trading
> remained profitable only when round-trip costs stayed below 0.4%. Enkhbayar and
> Ślepaczuk (2025) evaluated Random Forest, XGBoost, LSTM and other models against a
> moving-average strategy on six major currency pairs, including EUR/USD and GBP/USD, and
> found that no single strategy worked across all pairs: effectiveness was specific to
> each pair.
>
> Evidence on technical indicators is similarly cautious. Deep et al. (2025) applied
> Random Forest regression with technical indicators to minute-level SPY data across 13
> configurations; a strong in-sample fit turned negative out of sample, and returns fell
> below buy-and-hold. Pedersen and Crandall (2025) evaluated four families of
> machine-learning algorithms trading foreign exchange for small investors under
> realistic market simulation and concluded that consistent day-trading profit is
> difficult even for machine learning.
>
> On labelling and validation, Meyer et al. (2023) examined meta-labelling, in which a
> secondary model estimates the probability that a primary signal will succeed, and
> showed that calibrating that probability improves fixed position-sizing methods. Fu et
> al. (2024) extended the triple-barrier labelling method of López de Prado (2018),
> tuning the barriers with a genetic algorithm for pair trading in cryptocurrency
> markets: labels built for high profit raised profitability by 51.42%, while labels
> built for low risk reduced maximum drawdown by 73.24%. Arian et al. (2024) compared
> K-fold, purged K-fold, walk-forward and combinatorial purged cross-validation in a
> synthetic market and found that combinatorial purged cross-validation gave the lowest
> probability of backtest overfitting.
>
> Finally, Jongadsayakul (2024) analysed trading volumes in foreign exchange futures,
> including EUR/USD contracts, using vector autoregression and Granger causality, and
> found that EUR/USD futures volume moved independently of the other contracts. The study
> treats futures volume as a market statistic; it does not use volume as a filter for
> trading decisions. Table 2.2 summarises these studies.

---

## Part D: Chapter 2, new Table 2.2

Label **above** the table, description **below** it, as the supervisor asked.

**Table 2.2: Review of Recent Related Literature (2023–2025)**

| S/N | Author (Year) and Title | Problem Identified | Methodology | Solution Proffered | Remarks |
|---|---|---|---|---|---|
| 1 | López-Herrera et al. (2025). Directional forecasting for eight forex pairs against the US dollar using machine learning techniques | Which ML models stay profitable once realistic costs are charged | Seven models incl. Random Forest and XGBoost on 8 USD pairs, 2018–2023; time-series cross-validation; spread-based costs | Simpler models gave the best risk-adjusted returns; profitable only with costs below 0.4% | Supports cost-aware evaluation and interpretable models; no volume filter |
| 2 | Enkhbayar & Ślepaczuk (2025). Predictive modeling of foreign exchange trading signals using machine learning techniques | Whether ML signals beat trend-following on the major FX pairs | Random Forest, XGBoost, LSTM and others against a moving-average rule on six majors; walk-forward | No strategy worked on every pair; effectiveness is pair-specific | Mirrors this project's EUR/USD versus GBP/USD divergence |
| 3 | Deep et al. (2025). Risk-adjusted performance of random forest models in high-frequency trading | Whether technical indicators help at minute frequency | Random Forest with indicators on minute-level SPY data, 13 configurations | Good in-sample fit turned negative out of sample | Agrees with this project's rejection of RSI; supports a sealed test set |
| 4 | Pedersen & Crandall (2025). Can a machine learning model consistently learn profitable trading strategies in the forex market? | Profit claims rarely tested under realistic market simulation | Four families of ML algorithms trading FX in a realistic simulation | Consistent day-trading profit is hard even for machine learning | Supports cost-aware, sceptical evaluation with a no-skill baseline |
| 5 | Meyer et al. (2023). Meta-labeling: Calibration and position sizing | How to size positions from a secondary model's probability | Six sizing algorithms on calibrated and uncalibrated probabilities | Calibration improves fixed position-sizing methods | Formalises this project's rule-then-model design |
| 6 | Fu et al. (2024). Enhanced genetic-algorithm-driven triple barrier labeling method and machine learning approach for pair trading strategy in cryptocurrency markets | Classifiers need high-quality labels to trade well | Triple-barrier labels tuned by a genetic algorithm; cryptocurrency pairs | Profit up 51.42% or drawdown down 73.24%, depending on the labels | Confirms that barrier settings drive outcomes; not tested on FX |
| 7 | Arian et al. (2024). Backtest overfitting in the machine learning era | Standard out-of-sample tests let backtests overfit | K-fold, purged K-fold, walk-forward and combinatorial purged cross-validation compared | Combinatorial purged cross-validation gave the lowest overfitting | Supports rejecting K-fold; this project's walk-forward validation is a stated limitation |
| 8 | Jongadsayakul (2024). Dynamics of foreign exchange futures trading volumes in Thailand | How FX futures volumes interact | Vector autoregression and Granger causality on daily FX futures volumes, 2022–2024 | EUR/USD futures volume moves independently of other contracts | Uses volume as a statistic, not as a trade filter: the gap addressed here |

*Recent studies on machine-learning foreign exchange trading, labelling, validation and
exchange volume. Each entry was verified against its DOI record.*

---

## Part E: Chapter 2, §2.4 Identification of Research Gaps

Replace the numbered list in §2.4 with:

> A critical analysis of the reviewed literature, particularly the recent studies
> summarised in Table 2.2, reveals the following gaps:
>
> 1. **Results do not generalise.** Machine-learning performance in foreign exchange is
>    pair-specific and collapses out of sample (Deep et al., 2025; Enkhbayar & Ślepaczuk,
>    2025), so a model that performs well on one currency pair cannot be assumed to work
>    on another.
> 2. **Profit disappears under realistic evaluation.** Gains reported for machine-learning
>    trading vanish once transaction costs and realistic market simulation are applied
>    (López-Herrera et al., 2025; Pedersen & Crandall, 2025), yet many studies still
>    evaluate without them or without any measure of uncertainty.
> 3. **Validation still permits overfitting.** Commonly used test schemes allow backtests
>    to overfit (Arian et al., 2024), so reported results are rarely separated from
>    chance.
> 4. **Exchange volume is measured but not used.** Exchange-traded foreign exchange
>    futures volume is studied as a market statistic (Jongadsayakul, 2024) but not as a
>    filter for spot foreign exchange trades, although it is the most direct available
>    measure of institutional activity in a market with no central exchange.
> 5. **Rule-then-model designs are untested on intraday foreign exchange.** Meta-labelling
>    and triple-barrier labelling have been developed on equity and cryptocurrency data
>    (Fu et al., 2024; Meyer et al., 2023), not on hourly foreign exchange data.

---

## Part F: References to add (APA, alphabetical)

Arian, H., Norouzi Mobarekeh, D., & Seco, L. (2024). Backtest overfitting in the machine
learning era: A comparison of out-of-sample testing methods in a synthetic controlled
environment. *Knowledge-Based Systems, 305*, 112477.

Deep, A., Shirvani, A., Monico, C., Rachev, S., & Fabozzi, F. J. (2025). Risk-adjusted
performance of random forest models in high-frequency trading. *Journal of Risk and
Financial Management, 18*(3), 142.

Enkhbayar, S., & Ślepaczuk, R. (2025). Predictive modeling of foreign exchange trading
signals using machine learning techniques. *Expert Systems with Applications, 285*,
127729.

European Securities and Markets Authority. (2018). *Product intervention measures
relating to contracts for differences* (ESMA35-43-1135).

Fu, N., Kang, M., Hong, J., & Kim, S. (2024). Enhanced genetic-algorithm-driven triple
barrier labeling method and machine learning approach for pair trading strategy in
cryptocurrency markets. *Mathematics, 12*(5), 780.

Jongadsayakul, W. (2024). Dynamics of foreign exchange futures trading volumes in
Thailand. *Risks, 12*(9), 147.

López de Prado, M. (2018). *Advances in financial machine learning*. John Wiley & Sons.

López-Herrera, F., Jiménez, J. G. M., & Santiago, A. R. (2025). Directional forecasting
for eight forex pairs against the US dollar using machine learning techniques. *Discover
Artificial Intelligence, 5*(1), 224.

Meyer, M., Barziy, I., & Joubert, J. F. (2023). Meta-labeling: Calibration and position
sizing. *The Journal of Financial Data Science, 5*(2), 23–40.

Pedersen, E., & Crandall, J. W. (2025). Can a machine learning model consistently learn
profitable trading strategies in the forex market? In *2025 International Conference on
Machine Learning and Applications (ICMLA)* (pp. 742–747). IEEE.

**For Chapters 3 and 4** (the usability evaluation):

Brooke, J. (1996). SUS: A "quick and dirty" usability scale. In P. W. Jordan, B. Thomas,
B. A. Weerdmeester, & I. L. McClelland (Eds.), *Usability evaluation in industry*
(pp. 189–194). Taylor & Francis.

Sauro, J., & Lewis, J. R. (2016). *Quantifying the user experience: Practical statistics
for user research* (2nd ed.). Morgan Kaufmann.

**Correct this existing entry** (the authors' initials are wrong in the current list):

Chong, T. T. L., Ng, W. K., & Liew, V. K. S. (2014). Revisiting the performance of MACD
and RSI oscillators. *Journal of Risk and Financial Management, 7*(1), 1–12.

---

## Before you submit

- Open each DOI link once in a browser to confirm the details.
- López-Herrera et al. (2025): the DOI record lists the co-authors as Jiménez, J. G. M.
  and Santiago, A. R. Spanish double surnames are sometimes split differently in the
  published PDF, so check the first page of the paper and match it.
