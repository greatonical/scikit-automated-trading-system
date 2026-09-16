"""Build the 1-page progress report as a .docx (12pt, single spacing).

Keeps the .md as the source of truth; this just renders a Word file from the
same content, formatted to the supervisor's requirements (1 page, 12pt, single
line spacing). Run: .venv/bin/python scripts/make_progress_docx.py
"""
from pathlib import Path

from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "PROGRESS_REPORT_2026-06-17.docx"

doc = Document()

# Base style: 12pt, single spacing, tight margins so it fits one page.
normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(12)
pf = normal.paragraph_format
pf.line_spacing = 1.0
pf.space_after = Pt(4)

for section in doc.sections:
    section.top_margin = section.bottom_margin = Pt(36)      # 0.5"
    section.left_margin = section.right_margin = Pt(54)      # 0.75"


def heading(text, size=13):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(size)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    return p


def line(parts):
    """parts: list of (text, bold) tuples -> one paragraph."""
    p = doc.add_paragraph()
    for text, bold in parts:
        r = p.add_run(text)
        r.bold = bold
    return p


def bullet(parts, numbered=False):
    style = "List Number" if numbered else "List Bullet"
    p = doc.add_paragraph(style=style)
    for text, bold in parts:
        r = p.add_run(text)
        r.bold = bold
    p.paragraph_format.space_after = Pt(2)
    return p


# --- Title block ---
title = doc.add_paragraph()
tr = title.add_run("PROJECT PROGRESS REPORT")
tr.bold = True
tr.font.size = Pt(14)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
title.paragraph_format.space_after = Pt(6)

line([("Name: ", True), ("Awosusi Gabriel Ayomide", False)])
line([("Reg. No: ", True), ("CSC/2019/079", False)])
line([("Project Title: ", True),
      ("Design and Implementation of an Automated Financial Trading System", False)])

# --- 1 ---
heading("1. What I Have Done So Far")
line([("Literature Review (100%). ", True),
      ("Completed and written up in Chapters 1 to 3. It covers the problem of retail "
       "trading losses, the case for a hybrid Z-Score plus Random Forest approach over "
       "deep learning, and the UML design (class, use-case and sequence diagrams).", False)])
line([("Methodology and Design (100%). ", True),
      ("The modular architecture from Chapter 3 has been fully implemented. The analytical "
       "engine is kept separate from the execution layer, so data acquisition, preprocessing, "
       "the Random Forest model, the signal logic and risk management all run independently "
       "of MetaTrader 5.", False)])
line([("Implementation and Coding (about 90%). ", True),
      ("The full Python system is built and runs end to end. It fetches EUR/USD and GBP/USD "
       "data from Yahoo Finance, computes rolling Z-Scores, trains a Scikit-Learn Random Forest "
       "using a chronological 80/20 split with TimeSeriesSplit cross-validation, and generates "
       "trades only when both the Volume Z-Score exceeds +1.5 and the model is confident. It also "
       "includes fixed-fractional position sizing, a backtesting engine and a Streamlit dashboard. "
       "As evidence, the codebase has 163 automated tests, all passing, across 15 modules. The "
       "remaining 10% is running the live MetaTrader 5 terminal inside Docker against a demo "
       "account.", False)])
line([("Analysis (about 85%). ", True),
      ("I backtested the system on held-out data with spread and slippage included, using "
       "Scikit-Learn, pandas, NumPy and a custom backtester. The strongest result was that "
       "redefining the prediction target (a triple-barrier label that matches the actual "
       "stop-loss and take-profit exit) made both currency pairs profitable. GBP/USD reached a "
       "50% win rate with a profit factor of 2.42 and 2.7% maximum drawdown, and EUR/USD a 37% "
       "win rate with a profit factor of 1.42. I also tested adding RSI, MACD, ATR and other "
       "indicators, and found that none of them improved results on both pairs, which is a useful "
       "finding in itself.", False)])
line([("Chapters Drafted. ", True),
      ("Chapters 1 to 3 are final and I will send the current version by Friday 19 June. "
       "Chapter 4 (Implementation and Testing) has not been written yet, although the results "
       "and evidence it needs are already generated.", False)])

# --- 2 ---
heading("2. Most Difficult Aspects Remaining")
bullet([("Running the real MetaTrader 5 terminal headless under Wine in Docker and connecting "
         "it to a demo account. The code for this is built and tested against a simulated "
         "MetaTrader 5; the live broker connection is what remains.", False)], numbered=True)
bullet([("Writing Chapter 4 and Chapter 5, bringing in the backtest results and the indicator "
         "analysis.", False)], numbered=True)

# --- 3 ---
heading("3. Current Challenges & Support Needed")
line([("", False)]).add_run(
    "The main technical challenge was that the MetaTrader 5 library only runs on Windows while "
    "I develop on macOS. I solved this in the design by depending on an abstract interface and "
    "putting the real terminal in a Wine and Docker container, so the only step left there is "
    "the live demo run.")
line([("", False)]).add_run(
    "On the results, the system is profitable on its best configuration and keeps drawdown well "
    "within the 15% target, but the win rate sits below the 60% benchmark. I intend to present "
    "this honestly in Chapter 4 with a full explanation of why, rather than overstate the "
    "performance. I would appreciate your confirmation that this framing is acceptable and any "
    "steers on how much detail you want in the results section.")

# --- 4 ---
heading("4. Project Completion Plan")
line([("Target date for final draft submission to supervisor: ", True), ("Friday, 10 July 2026", False)])
line([("Target date for final project submission: ", True), ("Friday, 24 July 2026", False)])

table = doc.add_table(rows=1, cols=3)
table.style = "Table Grid"
hdr = table.rows[0].cells
for c, t in zip(hdr, ["Week", "Dates", "Focus"]):
    c.paragraphs[0].add_run(t).bold = True
rows = [
    ("1", "17 to 23 Jun", "Run the live MetaTrader 5 demo container, finalise results and figures, begin Chapter 4."),
    ("2", "24 to 30 Jun", "Complete Chapter 4 with results, tables and screenshots."),
    ("3", "1 to 7 Jul", "Write Chapter 5, and revise Chapters 1 to 3 based on your feedback."),
    ("4", "8 to 10 Jul", "Combine everything into a full draft and submit it to you by 10 July."),
]
for wk, dt, fo in rows:
    cells = table.add_row().cells
    cells[0].text, cells[1].text, cells[2].text = wk, dt, fo

# keep table font at 12pt
for row in table.rows:
    for cell in row.cells:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.size = Pt(11)

doc.add_paragraph()
line([("Declaration: ", True),
      ("I confirm that the above is a true reflection of my current progress.", False)])
line([("Name & Signature/Date: ", True),
      ("Awosusi Gabriel Ayomide  ______________  17 June 2026", False)])

doc.save(OUT)
print(f"Saved {OUT}")
