# Usability Study: Protocol, Questionnaire and Analysis

Closes the supervisor's requirement for "feedback and analysis from users" in Chapter 4
(`docs/SUPERVISOR_NOTES.md` §1): at least 50 respondents, a table of usability
criteria and a table of responses.

## 0. What is evaluated

The evaluated product is **Gadel**, the live system built from this research (approved
by the supervisor). It runs this project's execution architecture, risk management and
order-block logic; the Random Forest stays in the research system, whose backtest is
shown through the hosted dashboard below. Respondents are Gadel users.

Use real responses only. If fewer than 50 people respond, report the real number.

---

## 1. Put the dashboard online (about 10 minutes)

The repository is public and already contains the cached market data, so it deploys to
Streamlit Community Cloud as-is. Public-demo mode hides the broker credential boxes and
forces paper trading, so the page never collects or uses real account details.

1. Go to https://share.streamlit.io and sign in with the GitHub account that owns the repo.
2. **Create app** → repository `greatonical/scikit-automated-trading-system`, branch
   `main`, main file `dashboard/app.py`.
3. **Advanced settings** → Python version **3.12**. Under **Secrets**, paste:
   ```toml
   PUBLIC_DEMO = "true"
   ```
4. Deploy. When it loads, click **Run Backtest** once yourself: the first run trains the
   model (slower on the free tier); every visitor after that reuses it.
5. Check the sidebar says **Public Demo** and shows **no** login/password fields. Open it
   on a phone too.

---

## 2. What respondents do before answering (about 5 minutes)

Respondents are Gadel users answering about Gadel. Put these at the top of the form:

1. Use Gadel as normal: connect an account, view signals and the trade history.
2. Check the risk settings (position size, stop-loss, drawdown limits).
3. Optional: open the hosted dashboard link and click **Run Backtest** to see the
   research backtest behind the product.

---

## 3. The questionnaire (paste into Google Forms)

Keep the `Q1.` … `Q13.` prefixes exactly: the analysis script finds the columns by them.
Q1 to Q13 are **Linear scale 1 to 5**, labelled 1 = Strongly disagree, 5 = Strongly agree.

**Section A: About you** (anonymous: do not ask for names or emails)

- A1. Trading experience: None / Beginner / Intermediate / Advanced
- A2. Broker or platform you use most (optional, short answer)
- A3. How did you use the system? Hosted link / Watched a walkthrough
- A4. Consent: "I agree that my anonymous answers may be used in a final-year project."

**Section B: System Usability Scale** (Brooke, 1996)

- Q1. I think that I would like to use this system frequently.
- Q2. I found the system unnecessarily complex.
- Q3. I thought the system was easy to use.
- Q4. I think that I would need the support of a technical person to be able to use this system.
- Q5. I found the various functions in this system were well integrated.
- Q6. I thought there was too much inconsistency in this system.
- Q7. I would imagine that most people would learn to use this system very quickly.
- Q8. I found the system very cumbersome to use.
- Q9. I felt very confident using the system.
- Q10. I needed to learn a lot of things before I could get going with this system.

**Section C: This system**

- Q11. The system clearly shows why a trade was taken.
- Q12. I trust the system to execute trades automatically on my behalf.
- Q13. The risk controls (position sizing, stop-loss, drawdown limits) are useful.
- Q14. What would you improve? (paragraph, optional; quote themes in Chapter 4)

---

## 4. Analysis

Export the responses (Google Forms → Responses → Download CSV), then:

```bash
.venv/bin/python scripts/analyse_usability.py responses.csv
```

It prints Table A (criteria) and Table B (mean, SD and % agree per criterion), the SUS
score with a 95% confidence interval against the benchmark of 68, Cronbach's alpha, and
SUS by experience level. Paste the tables into Chapter 4 §4.3 and fill the "pending"
cells on the deck's *System Evaluation: Usability* slide.

Keep `responses.csv` out of the repository: it is personal data, even if anonymous.

## 5. How to write it up

- Report n, the recruitment channel (Gadel's trader community) and the access method.
- Interpret SUS against 68: above means better-than-average usability.
- Use Q14 for qualitative feedback: group the comments into themes, quote a few.
- State the limitations: a self-selected sample from one community, a short session,
  and paper trading only.
