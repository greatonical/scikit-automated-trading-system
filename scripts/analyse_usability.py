"""Analyse the usability questionnaire (protocol: docs/USABILITY_STUDY.md).

Input is the CSV exported from Google Forms. Question columns are matched by the
"Q1." to "Q13." prefix of their titles, so the wording itself can change; the
trading-experience column is any column whose title contains "experience".

Output (markdown, ready for Chapter 4 and the deck):
  * Table A: usability evaluation criteria
  * Table B: summary of responses (mean on a 1-5 scale, SD, % agree)
  * the System Usability Scale score with a 95% confidence interval
  * Cronbach's alpha for the 10 SUS items (questionnaire reliability)
  * SUS by trading experience

Scoring follows Brooke (1996). SUS items 2, 4, 6, 8 and 10 are negatively worded, so
they are reverse-scored (6 - x) before any criterion mean, making "higher = better"
throughout. "% agree" is the share of reverse-scored answers of 4 or 5.

Run it on REAL responses only. With fewer than 50 respondents it says so: report the
real n as a limitation rather than padding it.

usage: .venv/bin/python scripts/analyse_usability.py responses.csv
"""
from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd
from scipy import stats

TARGET_N = 50
SUS_BENCHMARK = 68.0          # Sauro & Lewis: average SUS across products
SUS_ITEMS = list(range(1, 11))
NEGATIVE = {2, 4, 6, 8, 10}
CRITERIA = [
    ("Ease of use", [2, 3, 8]),
    ("Learnability", [4, 7, 10]),
    ("Consistency", [5, 6]),
    ("Confidence", [9]),
    ("Clarity of trade explanation", [11]),
    ("Trust in the two-gate rule", [12]),
    ("Usefulness of risk limits", [13]),
]
LIKERT_WORDS = {
    "strongly disagree": 1, "disagree": 2, "neutral": 3,
    "neither agree nor disagree": 3, "agree": 4, "strongly agree": 5,
}


def _to_score(value) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip().lower()
    if text in LIKERT_WORDS:
        return float(LIKERT_WORDS[text])
    m = re.match(r"^\s*([1-5])\b", text)            # "5", "5 - Strongly agree"
    if m:
        return float(m.group(1))
    raise ValueError(f"unrecognised Likert answer: {value!r}")


def load(path: str) -> tuple[pd.DataFrame, pd.Series | None]:
    """Return (answers Q1..Q13 as floats, experience or None)."""
    raw = pd.read_csv(path)
    cols = {}
    for c in raw.columns:
        m = re.match(r"^\s*Q(\d{1,2})\b", str(c))
        if m and 1 <= int(m.group(1)) <= 13:
            cols[int(m.group(1))] = c
    missing = [q for q in range(1, 14) if q not in cols]
    if missing:
        raise ValueError(f"questionnaire columns not found for Q{missing}")
    answers = pd.DataFrame({q: raw[cols[q]].map(_to_score) for q in range(1, 14)})
    exp_cols = [c for c in raw.columns if "experience" in str(c).lower()]
    experience = raw[exp_cols[0]].astype(str).str.strip().str.lower() if exp_cols else None
    complete = answers[SUS_ITEMS].notna().all(axis=1)
    return answers[complete].reset_index(drop=True), (
        experience[complete].reset_index(drop=True) if experience is not None else None)


def positive(answers: pd.DataFrame) -> pd.DataFrame:
    """Reverse-score the negatively worded SUS items so higher is always better."""
    out = answers.copy()
    for q in NEGATIVE:
        out[q] = 6 - out[q]
    return out


def sus_scores(answers: pd.DataFrame) -> pd.Series:
    """Brooke (1996): odd items x-1, even items 5-x, summed and multiplied by 2.5."""
    contrib = sum((answers[q] - 1) if q % 2 else (5 - answers[q]) for q in SUS_ITEMS)
    return contrib * 2.5


def cronbach_alpha(items: pd.DataFrame) -> float:
    k = items.shape[1]
    item_var = items.var(axis=0, ddof=1).sum()
    total_var = items.sum(axis=1).var(ddof=1)
    if k < 2 or total_var == 0:
        return float("nan")
    return float(k / (k - 1) * (1 - item_var / total_var))


def mean_ci(x: pd.Series, level: float = 0.95) -> tuple[float, float, float]:
    x = x.dropna()
    m = float(x.mean())
    if len(x) < 2:
        return m, float("nan"), float("nan")
    half = stats.t.ppf((1 + level) / 2, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))
    return m, m - half, m + half


def criterion_rows(answers: pd.DataFrame) -> list[tuple[str, float, float, float]]:
    pos = positive(answers)
    rows = []
    for name, qs in CRITERIA:
        vals = pos[qs].stack().dropna()
        rows.append((name, float(vals.mean()), float(vals.std(ddof=1)),
                     float((vals >= 4).mean() * 100)))
    return rows


def report(answers: pd.DataFrame, experience: pd.Series | None = None) -> str:
    n = len(answers)
    if n == 0:
        raise ValueError("no complete responses")
    sus = sus_scores(answers)
    m, lo, hi = mean_ci(sus)
    alpha = cronbach_alpha(positive(answers)[SUS_ITEMS])
    lines = [f"Respondents with complete SUS answers: n = {n}"]
    if n < TARGET_N:
        lines.append(f"NOTE: n is below the target of {TARGET_N}. Report the real n and "
                     "state it as a limitation.")
    lines += [
        "",
        "Table A: Usability evaluation criteria",
        "",
        "| Criterion | Measured by |",
        "|---|---|",
        "| Overall usability | SUS items 1 to 10 (score 0 to 100) |",
    ]
    for name, qs in CRITERIA:
        label = ("SUS item" + ("s " if len(qs) > 1 else " ")
                 + ", ".join(map(str, qs))) if max(qs) <= 10 else f"Question {qs[0]}"
        lines.append(f"| {name} | {label} |")
    lines += [
        "",
        "Table B: Summary of responses",
        "",
        "| Criterion | Mean (1 to 5) | SD | % agree |",
        "|---|---|---|---|",
        f"| Overall SUS score | {m:.1f} / 100 (95% CI {lo:.1f} to {hi:.1f}) | "
        f"{sus.std(ddof=1):.1f} | benchmark {SUS_BENCHMARK:.0f} |",
    ]
    for name, mean, sd, agree in criterion_rows(answers):
        lines.append(f"| {name} | {mean:.2f} | {sd:.2f} | {agree:.0f}% |")
    verdict = "above" if lo > SUS_BENCHMARK else "below" if hi < SUS_BENCHMARK else \
        "not distinguishable from"
    lines += [
        "",
        f"SUS {m:.1f} is {verdict} the benchmark of {SUS_BENCHMARK:.0f} at 95% confidence.",
        f"Cronbach's alpha (10 SUS items) = {alpha:.2f} "
        f"({'acceptable' if alpha >= 0.7 else 'below the usual 0.7 threshold'}).",
    ]
    if experience is not None:
        lines += ["", "SUS by trading experience:", "",
                  "| Experience | n | Mean SUS |", "|---|---|---|"]
        for level, grp in sus.groupby(experience):
            lines.append(f"| {level} | {len(grp)} | {grp.mean():.1f} |")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: analyse_usability.py responses.csv")
    answers, experience = load(sys.argv[1])
    print(report(answers, experience))


if __name__ == "__main__":
    main()
