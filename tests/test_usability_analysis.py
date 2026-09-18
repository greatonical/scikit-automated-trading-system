"""Tests for scripts/analyse_usability.py.

The data here is synthetic and exists only to check the arithmetic; it is not, and
must never be reported as, a study result.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import analyse_usability as U  # noqa: E402


def _answers(rows):
    return pd.DataFrame(rows, columns=list(range(1, 14))).astype(float)


def test_sus_best_case_is_100():
    best = [5 if q % 2 else 1 for q in range(1, 11)] + [5, 5, 5]
    assert U.sus_scores(_answers([best]))[0] == pytest.approx(100)


def test_sus_worst_case_is_0():
    worst = [1 if q % 2 else 5 for q in range(1, 11)] + [1, 1, 1]
    assert U.sus_scores(_answers([worst]))[0] == pytest.approx(0)


def test_sus_all_neutral_is_50():
    assert U.sus_scores(_answers([[3] * 13]))[0] == pytest.approx(50)


def test_negative_items_are_reverse_scored():
    row = [3] * 13
    row[1] = 1                      # Q2 "unnecessarily complex": strongly disagree = good
    assert U.positive(_answers([row]))[2][0] == 5


def test_alpha_is_one_for_perfectly_consistent_items():
    items = pd.DataFrame({q: [1, 2, 3, 4, 5] for q in range(1, 11)}).astype(float)
    assert U.cronbach_alpha(items) == pytest.approx(1.0)


def test_criteria_use_reverse_scored_values():
    best = [5 if q % 2 else 1 for q in range(1, 11)] + [5, 5, 5]
    rows = {name: (mean, agree) for name, mean, _, agree
            in U.criterion_rows(_answers([best, best]))}
    assert rows["Ease of use"] == (5.0, 100.0)       # items 2, 3, 8 all "good"


def test_load_matches_google_forms_headers_and_word_answers(tmp_path):
    header = [f"Q{q}. question {q}" for q in range(1, 14)] + ["A1. Trading experience"]
    csv = tmp_path / "responses.csv"
    pd.DataFrame([["Strongly agree"] * 13 + ["Beginner"],
                  ["3"] * 13 + ["Advanced"]], columns=header).to_csv(csv, index=False)
    answers, experience = U.load(str(csv))
    assert answers.shape == (2, 13)
    assert answers.iloc[0, 0] == 5 and answers.iloc[1, 0] == 3
    assert list(experience) == ["beginner", "advanced"]


def test_report_flags_small_samples():
    out = U.report(_answers([[3] * 13, [4] * 13]))
    assert "below the target of 50" in out
    assert "Table B: Summary of responses" in out


def test_unrecognised_answer_is_an_error():
    with pytest.raises(ValueError):
        U._to_score("maybe")
