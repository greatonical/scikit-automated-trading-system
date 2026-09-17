"""Generate the CSC 504 defence presentation (docs/DEFENCE_PRESENTATION.pptx).

Every slide is built from native PowerPoint shapes — no images — so the author can
edit any box, label or word in PowerPoint. Diagrams follow standard notation:

  * Context diagram  — Level-0 DFD (Yourdon): one numbered process, external
    entities as rectangles, labelled data flows. No data stores at level 0.
  * Use case diagram — actors OUTSIDE a labelled system boundary, use cases as
    ellipses inside, solid association lines; <<include>> points from the base
    use case TO the included one, <<extend>> from the extending use case TO the base.
  * Activity diagram — filled initial node, rounded action nodes, diamond decisions
    with [guard] labels, ringed activity-final node.
  * Class diagram    — three compartments (name / attributes / operations), +public
    -private markers, generalization drawn as a hollow triangle at the superclass.

Figures are numbered and captioned "Figure N: ..." to match the department's sample.
Slides carry speaker notes. Screenshot slots are dashed placeholders the author fills.

Run:  .venv/bin/python scripts/make_defence_deck.py
Needs python-pptx (not a core dependency):  .venv/bin/pip install python-pptx

Font: the deck is set in Montserrat, which must be installed on the machine that OPENS
the file (it is installed in ~/Library/Fonts here). If you must present from a machine
without it, set FONT = "Arial" below and regenerate.

Keynote: the deck is built on docs/deck_base.pptx, NOT on python-pptx's bundled
template. python-pptx's notes master makes Keynote reject the whole file ("The file
format is invalid") as soon as any slide carries a speaker note; PowerPoint and Google
Slides accept it. This was isolated by driving Keynote from AppleScript: an otherwise
identical file opens, and adding one speaker note makes it fail. deck_base.pptx is a
real PowerPoint file with its slides and media stripped, so its notes master works.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pptx import Presentation                                    # noqa: E402
from pptx.dml.color import RGBColor                              # noqa: E402
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE            # noqa: E402
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN                  # noqa: E402
from pptx.oxml.ns import qn                                      # noqa: E402
from pptx.util import Emu, Inches, Pt                            # noqa: E402

OUT = ROOT / "docs" / "DEFENCE_PRESENTATION.pptx"

# Base template — see the Keynote note in the module docstring. Without it the deck
# still builds, but any machine running Keynote will refuse to open it.
BASE = ROOT / "docs" / "deck_base.pptx"
_R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #
W, H = Inches(10), Inches(5.625)
MARGIN = Inches(0.45)
CONTENT_W = Inches(9.10)
BODY_TOP = Inches(1.02)

# Montserrat (Regular + Bold) must be installed on whichever machine OPENS the file,
# or PowerPoint will substitute and the layout will shift. It is installed in
# ~/Library/Fonts on the author's machine; present from that laptop, or install it on
# the presenting machine. Set FONT = "Arial" for a guaranteed-everywhere fallback.
FONT = "Montserrat"

# Montserrat is noticeably wider than Arial at the same point size, so body text is
# scaled down slightly to keep the hand-placed layouts intact. Titles are untouched.
BODY_SCALE = 0.94
INK = RGBColor(0x1A, 0x1A, 0x1A)
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY = RGBColor(0x8A, 0x8A, 0x8A)
LIGHT = RGBColor(0xF2, 0xF4, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GOOD = RGBColor(0x1B, 0x6B, 0x3A)
BAD = RGBColor(0xA3, 0x1D, 0x1D)
ACCENT = RGBColor(0xD8, 0xE2, 0xEF)

_fig = {"n": 0}


def next_fig() -> int:
    _fig["n"] += 1
    return _fig["n"]


def _e(v):
    """Coerce a coordinate to INTEGER English Metric Units.

    Arithmetic such as ``w / 2`` yields a float in Python 3, and python-pptx writes
    it into the XML verbatim (e.g. ``y="1792224.0"``). ST_Coordinate is an integer
    type: PowerPoint tolerates the float, but Keynote and Google Slides reject the
    entire file. Every coordinate therefore passes through here before it reaches a
    shape constructor.
    """
    return Emu(int(round(float(v))))


# --------------------------------------------------------------------------- #
# Low-level helpers
# --------------------------------------------------------------------------- #
def _style_run(run, size=12, bold=False, color=INK, italic=False, mono=False):
    f = run.font
    f.name = "Consolas" if mono else FONT
    if not mono and size <= 13:          # body copy, labels, table cells
        size = round(size * BODY_SCALE, 1)
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color


def textbox(slide, x, y, w, h, text, size=12, bold=False, color=INK,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False, mono=False):
    tb = slide.shapes.add_textbox(_e(x), _e(y), _e(w), _e(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    _style_run(p.add_run(), size, bold, color, italic, mono)
    p.runs[0].text = text
    return tb


def bullets(slide, items, x=MARGIN, y=BODY_TOP, w=CONTENT_W, h=Inches(4.0),
            size=13, gap=6):
    """items: list of str or (text, level) or (text, level, bold)."""
    # Never let a text frame run off the bottom of the canvas.
    h = min(h, H - y - Inches(0.30))
    tb = slide.shapes.add_textbox(_e(x), _e(y), _e(w), _e(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    first = True
    for item in items:
        bold = False
        if isinstance(item, tuple):
            if len(item) == 3:
                text, level, bold = item
            else:
                text, level = item
        else:
            text, level = item, 0
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(gap)
        p.level = min(level, 4)
        marker = "" if level == 0 else ("–  " if level == 1 else "·  ")
        bullet = "•  " if level == 0 else marker
        r = p.add_run()
        r.text = bullet + text
        _style_run(r, size - (1 if level else 0), bold, INK if level == 0 else RGBColor(0x33, 0x33, 0x33))
    return tb


def _set_slide_size(prs, width, height):
    """Set the slide size AND clear the now-wrong ST_SlideSizeType attribute.

    python-pptx updates cx/cy when you change the slide size but leaves the default
    template's type="screen4x3" in place, so a 16:9 deck declares itself 4:3.
    PowerPoint ignores the contradiction; stricter readers (Keynote, Google Slides)
    can refuse the file. The attribute is optional in ECMA-376, so removing it is the
    safe fix — the real geometry is carried by cx/cy.
    """
    prs.slide_width, prs.slide_height = width, height
    try:
        el = prs._element
    except AttributeError:                      # pragma: no cover - API shift
        el = prs.part._element
    sld_sz = el.find(qn("p:sldSz"))
    if sld_sz is not None and "type" in sld_sz.attrib:
        del sld_sz.attrib["type"]


def _base_presentation():
    """Open the base template and remove any slides it ships with.

    Falls back to python-pptx's own template if the base is missing — the deck will
    build, but Keynote will not open it (see the module docstring).
    """
    if not BASE.exists():
        print(f"  ! WARNING: {BASE.name} missing — falling back to the python-pptx "
              f"template. The result will NOT open in Keynote.")
        return Presentation()
    prs = Presentation(str(BASE))
    sld_id_lst = prs.slides._sldIdLst
    for sld in list(sld_id_lst):
        prs.part.drop_rel(sld.get(_R_ID))
        sld_id_lst.remove(sld)
    return prs


def _blank_layout(prs):
    """The emptiest layout available in whatever template we are based on."""
    return min(prs.slide_layouts, key=lambda layout: len(layout.placeholders))


def add_slide(prs, title=None, number=True):
    slide = prs.slides.add_slide(_blank_layout(prs))
    # Drop any placeholders the layout carries: every element here is positioned
    # explicitly, and inherited "Click to add title" boxes would print.
    for ph in list(slide.placeholders):
        ph._element.getparent().remove(ph._element)
    if title:
        textbox(slide, MARGIN, Inches(0.26), CONTENT_W, Inches(0.5),
                title, size=22, bold=True, color=NAVY)
        rule = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, MARGIN, Inches(0.86), MARGIN + CONTENT_W, Inches(0.86))
        rule.line.color.rgb = ACCENT
        rule.line.width = Pt(1.5)
    if number:
        idx = len(prs.slides.__iter__.__self__._sldIdLst)
        textbox(slide, W - Inches(0.85), H - Inches(0.38), Inches(0.4), Inches(0.25),
                str(idx), size=10, color=GREY, align=PP_ALIGN.RIGHT)
    return slide


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def caption(slide, text, y=None):
    y = y or (H - Inches(0.62))
    textbox(slide, MARGIN, y, CONTENT_W, Inches(0.3), text,
            size=10, italic=True, color=RGBColor(0x44, 0x44, 0x44), align=PP_ALIGN.CENTER)


# --------------------------------------------------------------------------- #
# Shape primitives
# --------------------------------------------------------------------------- #
def box(slide, x, y, w, h, text, size=9, fill=WHITE, line=INK, bold=False,
        shape=MSO_SHAPE.RECTANGLE, color=INK, dash=False, line_w=1.0):
    sp = slide.shapes.add_shape(shape, _e(x), _e(y), _e(w), _e(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    sp.line.color.rgb = line
    sp.line.width = Pt(line_w)
    if dash:
        sp.line.dash_style = 4  # msoLineDash
    sp.shadow.inherit = False
    tf = sp.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.03)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        para = p if i == 0 else tf.add_paragraph()
        para.alignment = PP_ALIGN.CENTER
        r = para.add_run()
        r.text = ln
        _style_run(r, size, bold or i == 0 and len(lines) > 1, color)
    return sp


def line(slide, x1, y1, x2, y2, arrow=True, dash=False, color=INK, width=1.0,
         back_arrow=False):
    cn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, _e(x1), _e(y1), _e(x2), _e(y2))
    cn.line.color.rgb = color
    cn.line.width = Pt(width)
    if dash:
        cn.line.dash_style = 4
    ln = cn.line._get_or_add_ln()
    for tag, on in (("headEnd", back_arrow), ("tailEnd", arrow)):
        if not on:
            continue
        el = ln.find(qn("a:" + tag))
        if el is None:
            el = ln.makeelement(qn("a:" + tag), {})
            ln.append(el)
        el.set("type", "triangle")
        el.set("w", "med")
        el.set("len", "med")
    return cn


def label(slide, x, y, text, size=8, w=Inches(1.6), color=RGBColor(0x33, 0x33, 0x33)):
    return textbox(slide, x, y, w, Inches(0.2), text, size=size, color=color,
                   align=PP_ALIGN.CENTER)


def actor(slide, cx, top, name):
    """UML actor: stick figure + name beneath."""
    hd = Inches(0.17)
    box(slide, cx - hd / 2, top, hd, hd, "", shape=MSO_SHAPE.OVAL, line_w=1.0)
    body_top = top + hd
    line(slide, cx, body_top, cx, body_top + Inches(0.26), arrow=False)
    line(slide, cx - Inches(0.16), body_top + Inches(0.08),
         cx + Inches(0.16), body_top + Inches(0.08), arrow=False)
    line(slide, cx, body_top + Inches(0.26), cx - Inches(0.14), body_top + Inches(0.48), arrow=False)
    line(slide, cx, body_top + Inches(0.26), cx + Inches(0.14), body_top + Inches(0.48), arrow=False)
    textbox(slide, cx - Inches(0.7), body_top + Inches(0.52), Inches(1.4), Inches(0.2),
            name, size=8, align=PP_ALIGN.CENTER)


def class_box(slide, x, y, w, name, attrs, ops, h_name=Inches(0.26),
              row=Inches(0.17), italic_name=False):
    """Three-compartment UML class."""
    sp = box(slide, x, y, w, h_name, name, size=9, bold=True, fill=LIGHT)
    if italic_name:
        for p in sp.text_frame.paragraphs:
            for r in p.runs:
                r.font.italic = True
    ah = row * max(len(attrs), 1)
    oh = row * max(len(ops), 1)
    for items, top, hh in ((attrs, y + h_name, ah), (ops, y + h_name + ah, oh)):
        cell = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, _e(x), _e(top), _e(w), _e(hh))
        cell.fill.solid()
        cell.fill.fore_color.rgb = WHITE
        cell.line.color.rgb = INK
        cell.line.width = Pt(1.0)
        cell.shadow.inherit = False
        tf = cell.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.04)
        tf.margin_right = Inches(0.02)
        tf.margin_top = tf.margin_bottom = Inches(0.01)
        tf.vertical_anchor = MSO_ANCHOR.TOP
        for i, it in enumerate(items or [" "]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = it
            _style_run(r, 7.5)
    return y + h_name + ah + oh


def generalization(slide, x_child_top_cx, y_child_top, x_parent_cx, y_parent_bottom):
    """UML generalization: line from child to a hollow triangle at the parent."""
    tri_w, tri_h = Inches(0.16), Inches(0.13)
    line(slide, x_child_top_cx, y_child_top, x_parent_cx, y_parent_bottom + tri_h,
         arrow=False)
    box(slide, x_parent_cx - tri_w / 2, y_parent_bottom, tri_w, tri_h, "",
        shape=MSO_SHAPE.ISOSCELES_TRIANGLE, fill=WHITE)


def placeholder(slide, x, y, w, h, what):
    box(slide, x, y, w, h, "", fill=RGBColor(0xFA, 0xFB, 0xFC), line=GREY, dash=True)
    textbox(slide, x, y + h / 2 - Inches(0.28), w, Inches(0.24),
            "[  INSERT SCREENSHOT  ]", size=11, bold=True, color=GREY,
            align=PP_ALIGN.CENTER)
    textbox(slide, x + Inches(0.15), y + h / 2 + Inches(0.02), w - Inches(0.3), Inches(0.5),
            what, size=9, color=GREY, align=PP_ALIGN.CENTER)


def table(slide, data, x, y, w, h, col_w=None, head_size=9, body_size=9,
          mark_cols=()):
    rows, cols = len(data), len(data[0])
    shape = slide.shapes.add_table(rows, cols, _e(x), _e(y), _e(w), _e(h))
    tbl = shape.table
    if col_w:
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = _e(cw)
    for r, row in enumerate(data):
        tbl.rows[r].height = _e(Inches(0.26))
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.05)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if r == 0 else (
                WHITE if r % 2 else RGBColor(0xF7, 0xF9, 0xFB))
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if c else PP_ALIGN.LEFT
            r_ = p.add_run()
            r_.text = str(val)
            colour = WHITE if r == 0 else INK
            if r and c in mark_cols:
                if "PASS" in str(val) or "✓" in str(val):
                    colour = GOOD
                elif "FAIL" in str(val) or "✗" in str(val):
                    colour = BAD
            _style_run(r_, head_size if r == 0 else body_size, r == 0, colour)
    return tbl


# =========================================================================== #
# Slides
# =========================================================================== #
def s_title(prs):
    s = add_slide(prs, number=False)
    box(s, Emu(0), Emu(0), W, Inches(0.12), "", fill=NAVY, line=NAVY)
    textbox(s, MARGIN, Inches(0.75), CONTENT_W, Inches(0.4),
            "CSC 504 PRESENTATION", size=15, bold=True, color=GREY, align=PP_ALIGN.CENTER)
    textbox(s, MARGIN, Inches(1.25), CONTENT_W, Inches(1.5),
            "DESIGN AND IMPLEMENTATION OF AN AUTOMATED\n"
            "FINANCIAL TRADING SYSTEM FOR THE\nFOREIGN EXCHANGE MARKET",
            size=26, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    tb = s.shapes.add_textbox(MARGIN, Inches(2.75), CONTENT_W, Inches(0.9))
    tf = tb.text_frame
    for i, ln in enumerate([
        "A hybrid Volume Z-Score + Random Forest approach,",
        "evaluated on held-out data with transaction costs",
    ]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = ln
        _style_run(r, 12, False, RGBColor(0x44, 0x44, 0x44), italic=True)

    line(s, Inches(3.6), Inches(3.72), Inches(6.4), Inches(3.72), arrow=False, color=ACCENT, width=1.5)
    tb = s.shapes.add_textbox(MARGIN, Inches(3.9), CONTENT_W, Inches(1.2))
    tf = tb.text_frame
    for i, (lbl, val) in enumerate([
        ("Name:", "AWOSUSI GABRIEL AYOMIDE"),
        ("Matric No:", "CSC/2019/079"),
        ("Supervisor:", "_______________________"),
    ]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        p.space_after = Pt(3)
        r1 = p.add_run(); r1.text = lbl + "  "
        _style_run(r1, 12, False, GREY)
        r2 = p.add_run(); r2.text = val
        _style_run(r2, 12, True, INK)
    notes(s, "Greet the panel. State the title, then one sentence: the system combines a "
             "statistical volume filter with a Random Forest, and every number reported "
             "comes from held-out data with spread and slippage charged.")


def s_outline(prs):
    s = add_slide(prs, "Presentation Outline")
    left = ["INTRODUCTION", "STATEMENT OF PROBLEM", "AIM AND OBJECTIVES",
            "LITERATURE REVIEW", "METHODOLOGY", "JUSTIFICATION", "SCOPE OF PROJECT"]
    right = ["WORK DONE — DESIGN SPECIFICATION", "WORK DONE — IMPLEMENTATION & RESULTS",
             "FROM RESEARCH TO A LIVE PRODUCT", "CONTRIBUTION TO KNOWLEDGE",
             "WORK LEFT UNDONE", "CONCLUSION", "REFERENCES"]
    for col, items, x in ((0, left, MARGIN), (1, right, Inches(5.15))):
        tb = s.shapes.add_textbox(x, BODY_TOP + Inches(0.15), Inches(4.4), Inches(3.8))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, it in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(9)
            r = p.add_run()
            r.text = f"{i + 1 + col * len(left):2d}.   {it}"
            _style_run(r, 12, False, INK)
    notes(s, "Keep this to fifteen seconds. Point out that the second column is where the "
             "evidence lives — design, results, and the live product.")


def s_intro1(prs):
    s = add_slide(prs, "Introduction")
    bullets(s, [
        "The foreign exchange market is the largest financial market in the world, "
        "trading over US$7 trillion per day, and it is open 24 hours a day, five days a week.",
        "Retail participation has grown rapidly, but the outcomes are poor: regulators "
        "report that a large majority of retail accounts lose money (ESMA, 2018).",
        "Two causes dominate — emotional decision-making under pressure, and the "
        "impossibility of a human monitoring a 24-hour market consistently.",
        "Algorithmic trading removes the emotional element and enforces a rule set "
        "identically on every candle, which is why institutional participants adopted it first.",
        ("This project asks a narrower, testable question:", 0, True),
        ("Can a statistical filter combined with a machine-learning classifier produce "
         "a trading rule whose performance can be honestly measured on unseen data?", 1),
    ], size=12.5)
    notes(s, "Set up the problem in plain language. The last bullet is the framing the "
             "whole defence rests on: the contribution is a measurable method, not a "
             "promise of profit.")


def s_intro2(prs):
    s = add_slide(prs, "Introduction (cont'd)")
    bullets(s, [
        ("Why a rule filter AND a model, rather than either alone?", 0, True),
        ("A pure rule system (e.g. moving-average crossover) cannot adapt — it fires "
         "the same way in every market condition.", 1),
        ("A pure machine-learning system trades constantly and is hard to defend: it "
         "gives no human-readable reason for any single decision.", 1),
        ("The hybrid design requires BOTH to agree, so every trade has a stated "
         "statistical reason and a model probability attached to it.", 1),
        ("Why the Random Forest and not deep learning?", 0, True),
        ("Runs on CPU-only hardware; resists overfitting through ensemble averaging; "
         "and exposes feature importances, so the model can be interrogated.", 1),
        ("Deep learning (LSTM) was reviewed and deliberately rejected — see Literature "
         "Review — on grounds of compute cost and opacity, not ignorance.", 1),
    ], size=12.5)
    notes(s, "If a panel member asks 'why not an LSTM?', this slide is the answer and it "
             "is already in Chapter 2. Interpretability is a stated project goal.")


def s_problem(prs):
    s = add_slide(prs, "Statement of the Problem")
    bullets(s, [
        "Retail traders lose money predominantly because decisions are emotional, "
        "inconsistent, and cannot be sustained across a 24-hour market.",
        "Existing retail automation is largely rule-only: it cannot weigh evidence, "
        "and it repeats the same behaviour regardless of market state.",
        "Published machine-learning trading results are frequently not reproducible — "
        "they omit transaction costs, shuffle time-series data (which leaks the future "
        "into training), or report only the best run.",
        "Most critically, results are rarely reported with any measure of uncertainty, "
        "so a strong-looking win rate cannot be distinguished from luck.",
        ("The gap this project addresses:", 0, True),
        ("A transparent hybrid system whose every claim is measured on a sealed test "
         "set, with costs charged, confidence intervals quoted, and negative results "
         "reported rather than discarded.", 1),
    ], size=12.5)
    notes(s, "The third and fourth bullets are your differentiator. Most projects in this "
             "area cannot say them. Say them slowly.")


def s_aim(prs):
    s = add_slide(prs, "Aim and Objectives")
    textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.7),
            "Aim:  to design, implement and evaluate an automated financial trading "
            "system for the foreign exchange market that combines statistical filtering "
            "with machine-learning prediction, and to report its performance honestly.",
            size=12.5, bold=False)
    textbox(s, MARGIN, BODY_TOP + Inches(0.78), CONTENT_W, Inches(0.25),
            "The specific objectives are:", size=12.5, bold=True)
    bullets(s, [
        ("i.   To design a hybrid decision model in which a Volume Z-Score rule and a "
         "Random Forest classifier must both agree before any trade is taken.", 0),
        ("ii.  To implement the system end to end — data acquisition, feature "
         "engineering, labelling, training, signal generation, risk management and "
         "order execution.", 0),
        ("iii. To integrate a risk-management layer providing fixed-fractional position "
         "sizing, dynamic stop-losses and hard account-level limits.", 0),
        ("iv.  To evaluate the system by backtesting on held-out data with transaction "
         "costs, against defined targets for win rate, profit factor, drawdown and "
         "Sharpe ratio.", 0),
    ], y=BODY_TOP + Inches(1.08), size=12)
    notes(s, "Objective (iv) is the one to emphasise: the project is judged by whether the "
             "evaluation is sound, not by whether the numbers are flattering.")


def s_litreview(prs, rows, part):
    s = add_slide(prs, f"Literature Review ({part})")
    data = [["S/N", "Author / Title", "Method", "Finding", "Comment (this project)"]] + rows
    table(s, data, MARGIN, BODY_TOP + Inches(0.05), CONTENT_W, Inches(3.4),
          col_w=[Inches(0.42), Inches(2.25), Inches(1.75), Inches(2.1), Inches(2.58)],
          head_size=9, body_size=8)
    return s


def s_lit1(prs):
    s = s_litreview(prs, [
        ["1", "Lopez de Prado (2018): Advances in Financial Machine Learning",
         "Triple-barrier labelling; meta-labelling",
         "Naive next-candle labels do not match how trades actually close",
         "ADOPTED. The single most effective change made — it turned both currency "
         "pairs from a net loss into a net profit."],
        ["2", "Chong, Ng & Liew (2014): Technical indicators as ML inputs",
         "RSI / MACD as model features",
         "Indicators can add predictive value in some markets",
         "TESTED AND REJECTED. Both reduced win rate and profit factor on both "
         "pairs; kept in code, switched off."],
        ["3", "Sirignano & Cont (2019): Universal features of price formation",
         "Deep learning on limit-order-book data",
         "Order-flow / institutional footprints carry signal",
         "Motivated the volume filter and the order-block test (Step F)."],
    ], "1 of 2")
    notes(s, "The 'Comment' column is the important one — it shows you engaged with each "
             "paper and measured its claim rather than citing it decoratively.")


def s_lit2(prs):
    s = s_litreview(prs, [
        ["4", "Hu, Zhao & Khushi (2021); Yildirim et al. (2021): LSTM for FX",
         "Deep recurrent networks on price series",
         "Report gains for FX direction prediction",
         "REVIEWED, NOT ADOPTED — CPU-only hardware, and the opacity conflicts "
         "with this project's interpretability goal."],
        ["5", "Bailey et al. (2014): The probability of backtest overfitting",
         "Statistical critique of backtesting",
         "Repeated tuning on one dataset inflates apparent performance",
         "ADOPTED AS DISCIPLINE. Chronological split, TimeSeriesSplit CV, and a "
         "sealed test set used once."],
        ["6", "Barber & Odean (2000): Trading is hazardous to your wealth",
         "Study of retail brokerage accounts",
         "Frequent retail trading systematically underperforms",
         "Motivates the selective AND-gate: the system trades on roughly 1.3% of "
         "candles, not continuously."],
    ], "2 of 2")
    notes(s, "Bailey et al. is your defence against 'did you overfit?'. The answer is a "
             "process answer, and it was designed in from the start.")


def s_methodology(prs):
    s = add_slide(prs, "Methodology")
    bullets(s, [
        ("Approach:", 0, True),
        ("Experimental and incremental — build one module at a time, measure every "
         "change on BOTH currency pairs, and record the result whether it helped or not.", 1),
        ("Data:", 0, True),
        ("Hourly EUR/USD and GBP/USD candles from Yahoo Finance. Because spot FX has "
         "no central exchange and reports zero volume, volume is taken from the "
         "matching CME currency futures (6E=F, 6B=F) — the standard proxy for "
         "institutional activity.", 1),
        ("Model:", 0, True),
        ("Random Forest classifier (scikit-learn), tuned with TimeSeriesSplit "
         "cross-validation on the training portion only.", 1),
        ("Evaluation:", 0, True),
        ("Event-driven backtest on the held-out 20% of the timeline, with spread and "
         "slippage charged on both entry and exit; win rates quoted with Wilson "
         "confidence intervals and compared against a no-skill baseline.", 1),
        ("Tools:", 0, True),
        ("Python 3.14, scikit-learn, pandas, Streamlit dashboard, Docker; 231 "
         "automated tests, including anti-leakage tests for every feature.", 1),
    ], size=11.5, gap=4)
    notes(s, "The anti-leakage tests are worth naming aloud: each one deletes future rows "
             "and asserts that past feature values do not change.")


def s_justification(prs):
    s = add_slide(prs, "Justification")
    bullets(s, [
        "Removes emotional and fatigue-driven error from execution — the dominant "
        "documented cause of retail losses.",
        "The hybrid AND-gate makes every decision explainable: each trade carries the "
        "volume Z-Score that triggered it and the model probability that confirmed it, "
        "so no decision is a black box.",
        "Risk management is enforced by the system rather than by the trader's "
        "discipline: position size is a fixed fraction of equity, and hard drawdown and "
        "daily-loss limits stop trading automatically.",
        "The evaluation method is itself a contribution — it is reproducible, costed, "
        "and reports negative results, which is uncommon in this literature.",
        "The architecture separates the analytical engine from the broker, so the same "
        "tested engine runs against a simulated broker or a real one with a single "
        "configuration change and no code edits.",
    ], size=12.5)
    notes(s, "Bullet four is the academic justification; bullet five is the engineering "
             "justification. Both matter to this panel.")


def s_scope(prs):
    s = add_slide(prs, "Scope of the Project")
    bullets(s, [
        ("In scope:", 0, True),
        ("Two currency pairs — EUR/USD and GBP/USD — on the 1-hour timeframe.", 1),
        ("A complete pipeline: data handling, feature engineering, labelling, model "
         "training, signal generation, risk management, order execution, backtesting "
         "and a monitoring dashboard.", 1),
        ("Evaluation by backtesting on held-out data, plus live execution validation "
         "on a broker demo account.", 1),
        ("Out of scope:", 0, True),
        ("Trading with real money. The system is restricted to demo accounts, and this "
         "is enforced in code, not merely by policy.", 1),
        ("High-frequency or tick-level trading; the system operates on hourly candles.", 1),
        ("Portfolio optimisation across many instruments, and deep-learning models.", 1),
        ("Limitation acknowledged:", 0, True),
        ("Yahoo Finance serves only about 730 days of hourly data, so the study window "
         "is approximately two years rather than the five originally planned.", 1),
    ], size=12, gap=4)
    notes(s, "State the data limitation yourself before anyone asks. It is a documented "
             "property of the data source, not a design flaw.")


def s_workdone_overview(prs):
    s = add_slide(prs, "Work Done")
    textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.3),
            "The system is fully implemented, tested and evaluated. This section covers:",
            size=12.5)
    cols = [
        ("Design Specification", ["Context Diagram", "System Architecture",
                                  "Block Diagram", "Use Case Diagram",
                                  "Activity Diagram", "Class Diagram"]),
        ("Implementation", ["13 modules, Python 3.14", "231 automated tests, all passing",
                            "Streamlit dashboard", "Docker deployment",
                            "Live MT5 execution path", "Demo-only safety guards"]),
        ("Evaluation", ["Held-out backtest, both pairs", "Costs charged on every trade",
                        "Wilson confidence intervals", "No-skill baseline comparison",
                        "Six measured negative results", "Live execution validation"]),
    ]
    x = MARGIN
    for head, items in cols:
        box(s, x, BODY_TOP + Inches(0.45), Inches(2.9), Inches(0.35), head,
            size=11, bold=True, fill=NAVY, line=NAVY, color=WHITE)
        tb = s.shapes.add_textbox(x + Inches(0.1), BODY_TOP + Inches(0.92),
                                  Inches(2.75), Inches(2.3))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, it in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(6)
            r = p.add_run()
            r.text = "•  " + it
            _style_run(r, 10)
        x += Inches(3.1)
    notes(s, "This is the map for the next twelve slides. Say: 'the design is not a "
             "proposal — all of it is built and measured.'")


# --------------------------------------------------------------------------- #
# Diagrams
# --------------------------------------------------------------------------- #
def s_context(prs):
    s = add_slide(prs, "Design Specification — Context Diagram")
    cx, cy = Inches(4.62), Inches(2.45)
    box(s, cx, cy, Inches(1.9), Inches(1.0),
        "0\nAutomated Financial\nTrading System", size=9, bold=True,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)

    ents = [
        (Inches(0.62), Inches(1.30), "Market Data\nProvider\n(Yahoo Finance / CME)"),
        (Inches(0.62), Inches(3.35), "Trader\n(User)"),
        (Inches(7.55), Inches(1.30), "Broker\n(MetaTrader 5)"),
        (Inches(7.55), Inches(3.35), "Model &\nLog Store"),
    ]
    for x, y, t in ents:
        box(s, x, y, Inches(1.85), Inches(0.72), t, size=8.5)

    line(s, Inches(2.47), Inches(1.66), cx, Inches(2.70))
    label(s, Inches(2.35), Inches(1.95), "OHLCV + volume")

    line(s, Inches(2.47), Inches(3.62), cx, Inches(3.15))
    label(s, Inches(2.35), Inches(3.68), "configuration / parameters")

    line(s, cx + Inches(1.9), Inches(2.70), Inches(7.55), Inches(1.66))
    label(s, Inches(6.55), Inches(1.95), "order (side, size, SL, TP)")

    line(s, Inches(7.55), Inches(1.90), cx + Inches(1.9), Inches(2.90), back_arrow=False)
    label(s, Inches(6.62), Inches(2.42), "fill confirmation")

    line(s, cx + Inches(1.9), Inches(3.15), Inches(7.55), Inches(3.62))
    label(s, Inches(6.60), Inches(3.70), "trained model, decision log")

    line(s, cx, Inches(2.95), Inches(2.47), Inches(3.95), arrow=True)
    label(s, Inches(2.30), Inches(3.30), "signals, metrics, dashboard")

    caption(s, f"Figure {next_fig()}: Context Diagram (Level-0 Data Flow Diagram) of the "
               f"Automated Financial Trading System")
    notes(s, "Standard Level-0 DFD: exactly one process, external entities as rectangles, "
             "labelled data flows, and no internal data stores at this level. Point out "
             "that the broker is an external entity — that is what makes it swappable.")


def s_architecture(prs):
    s = add_slide(prs, "Design Specification — System Architecture")
    x0, w0 = Inches(1.45), Inches(7.1)
    layers = [
        ("Layer 1", "Presentation Layer", ["Streamlit Dashboard", "Backtest Mode", "Live Mode"]),
        ("Layer 2", "Application Layer", ["Signal Generator", "Risk Manager", "Backtester"]),
        ("Layer 3", "Domain / Model Layer", ["Preprocessor", "Random Forest Model", "Labeller"]),
        ("Layer 4", "Infrastructure Layer", ["Data Handler", "Execution Handler", "Persistence"]),
    ]
    y = BODY_TOP + Inches(0.12)
    hh = Inches(0.78)
    for tag, name, comps in layers:
        box(s, Inches(0.55), y, Inches(0.82), hh, tag, size=8.5, bold=True, fill=LIGHT)
        box(s, x0, y, w0, hh, "", fill=WHITE)
        textbox(s, x0 + Inches(0.1), y + Inches(0.05), Inches(2.0), Inches(0.2),
                name, size=9, bold=True, color=NAVY)
        cw = Inches(2.05)
        cx = x0 + Inches(0.12)
        for c in comps:
            box(s, cx, y + Inches(0.29), cw, Inches(0.38), c, size=8.5,
                shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=RGBColor(0xF7, 0xF9, 0xFB))
            cx += cw + Inches(0.18)
        y += hh + Inches(0.10)

    box(s, Inches(8.72), BODY_TOP + Inches(0.12), Inches(0.72), Inches(3.42),
        "C\no\nn\nf\ni\ng", size=8, fill=ACCENT)
    caption(s, f"Figure {next_fig()}: Four-layer System Architecture. Each layer depends "
               f"only on the layer beneath it.")
    notes(s, "The rule that matters: nothing above Layer 4 knows which broker is in use. "
             "That is what makes mock-versus-real a one-line configuration change.")


def s_block(prs):
    s = add_slide(prs, "Design Specification — Block Diagram")
    blocks = ["Data\nHandler", "Pre-\nprocessor", "Random\nForest", "Signal\nGenerator",
              "Risk\nManager", "Execution\nHandler"]
    x = Inches(0.42)
    w, h = Inches(1.33), Inches(0.82)
    y = Inches(1.55)
    centres = []
    for i, b in enumerate(blocks):
        box(s, x, y, w, h, b, size=9, bold=True,
            shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
        centres.append(x + w / 2)
        if i:
            line(s, x - Inches(0.19), y + h / 2, x - Inches(0.02), y + h / 2)
        x += w + Inches(0.19)
    sub = ["fetch,\nclean, cache", "Z-scores,\nindicators", "P(bullish)",
           "AND-gate\nBUY/SELL/HOLD", "size, SL/TP,\nlimits", "mock | MT5 |\nRPC"]
    x = Inches(0.42)
    for t in sub:
        textbox(s, x, y + h + Inches(0.08), w, Inches(0.5), t, size=7.5,
                color=RGBColor(0x55, 0x55, 0x55), align=PP_ALIGN.CENTER)
        x += w + Inches(0.19)

    box(s, Inches(0.42), Inches(3.25), Inches(3.5), Inches(0.5),
        "Triple-Barrier Labeller\n(training target)", size=8.5, fill=RGBColor(0xFA, 0xF6, 0xEC))
    line(s, Inches(2.17), Inches(3.25), Inches(2.17), Inches(2.42))
    box(s, Inches(5.7), Inches(3.25), Inches(3.68), Inches(0.5),
        "Backtester  —  replays history, charges spread + slippage", size=8.5,
        fill=RGBColor(0xFA, 0xF6, 0xEC))
    line(s, Inches(7.54), Inches(3.25), Inches(7.54), Inches(2.42))
    caption(s, f"Figure {next_fig()}: Block Diagram of the processing pipeline")
    notes(s, "Walk left to right in one sentence per block. Stress that the labeller feeds "
             "training only, and the backtester consumes the same pipeline as live trading.")


def s_usecase(prs):
    s = add_slide(prs, "Design Specification — Use Case Diagram")
    bx, by, bw, bh = Inches(2.35), Inches(1.12), Inches(5.25), Inches(3.45)
    box(s, bx, by, bw, bh, "", fill=WHITE, line=GREY)
    textbox(s, bx + Inches(0.1), by + Inches(0.06), Inches(3.0), Inches(0.2),
            "Automated Trading System", size=9, bold=True, color=GREY)

    ucs = [
        ("Configure\nparameters", Inches(2.62), Inches(1.45)),
        ("Run backtest", Inches(2.62), Inches(2.05)),
        ("View results\n& metrics", Inches(2.62), Inches(2.65)),
        ("Train model", Inches(5.10), Inches(1.45)),
        ("Generate\nsignal", Inches(5.10), Inches(2.05)),
        ("Place order", Inches(5.10), Inches(2.65)),
        ("Monitor\npositions", Inches(2.62), Inches(3.25)),
        ("Enforce risk\nlimits", Inches(5.10), Inches(3.25)),
    ]
    pos = {}
    for t, x, y in ucs:
        box(s, x, y, Inches(1.95), Inches(0.5), t, size=8, shape=MSO_SHAPE.OVAL)
        pos[t] = (x, y)

    actor(s, Inches(1.15), Inches(1.75), "Trader")
    actor(s, Inches(8.65), Inches(1.55), "Broker\n(MT5)")
    actor(s, Inches(8.65), Inches(3.05), "Market Data\nProvider")

    for t in ("Configure\nparameters", "Run backtest", "View results\n& metrics",
              "Monitor\npositions"):
        x, y = pos[t]
        line(s, Inches(1.35), Inches(2.15), x, y + Inches(0.25), arrow=False)
    line(s, Inches(8.45), Inches(1.95), Inches(7.05), Inches(2.90), arrow=False)
    line(s, Inches(8.45), Inches(3.45), Inches(4.57), Inches(1.70), arrow=False)

    # <<include>>: base --> included
    x1, y1 = pos["Run backtest"]
    x2, y2 = pos["Train model"]
    line(s, x1 + Inches(1.95), y1 + Inches(0.25), x2, y2 + Inches(0.25), dash=True)
    label(s, Inches(4.28), Inches(1.80), "«include»", size=7.5, w=Inches(1.0))

    x1, y1 = pos["Generate\nsignal"]
    x2, y2 = pos["Place order"]
    line(s, x1 + Inches(0.97), y1 + Inches(0.5), x2 + Inches(0.97), y2, dash=True)
    label(s, Inches(6.05), Inches(2.56), "«include»", size=7.5, w=Inches(1.0))

    # <<extend>>: extending --> base
    x1, y1 = pos["Enforce risk\nlimits"]
    x2, y2 = pos["Place order"]
    line(s, x1 + Inches(0.5), y1, x2 + Inches(0.5), y2 + Inches(0.5), dash=True)
    label(s, Inches(4.35), Inches(3.08), "«extend»", size=7.5, w=Inches(1.0))

    caption(s, f"Figure {next_fig()}: Use Case Diagram. Solid lines are associations; "
               f"dashed arrows carry «include» / «extend» stereotypes.")
    notes(s, "Notation check if asked: actors sit outside the boundary; «include» points "
             "from the base use case to the one it always invokes; «extend» points from "
             "the optional behaviour back to the base use case it may extend.")


def s_activity(prs):
    s = add_slide(prs, "Design Specification — Activity Diagram")
    cx = Inches(2.05)
    box(s, cx - Inches(0.09), Inches(1.10), Inches(0.18), Inches(0.18), "",
        shape=MSO_SHAPE.OVAL, fill=INK, line=INK)

    acts = [
        ("Fetch latest closed candle", Inches(1.38)),
        ("Compute Z-scores & features", Inches(2.00)),
        ("Predict P(bullish) with Random Forest", Inches(2.62)),
    ]
    for t, y in acts:
        box(s, cx - Inches(1.30), y, Inches(2.60), Inches(0.42), t, size=8.5,
            shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
    line(s, cx, Inches(1.28), cx, Inches(1.38))
    line(s, cx, Inches(1.80), cx, Inches(2.00))
    line(s, cx, Inches(2.42), cx, Inches(2.62))

    d1y = Inches(3.24)
    box(s, cx - Inches(0.62), d1y, Inches(1.24), Inches(0.62), "Volume Z\n> 1.5 ?",
        size=8, shape=MSO_SHAPE.DIAMOND, fill=WHITE)
    line(s, cx, Inches(3.04), cx, d1y)

    d2x = Inches(5.05)
    box(s, d2x - Inches(0.62), d1y, Inches(1.24), Inches(0.62), "P(bullish)\n> 0.55 ?",
        size=8, shape=MSO_SHAPE.DIAMOND, fill=WHITE)
    line(s, cx + Inches(0.62), d1y + Inches(0.31), d2x - Inches(0.62), d1y + Inches(0.31))
    label(s, Inches(3.05), Inches(3.30), "[yes]", size=8, w=Inches(0.8))

    hold_y = Inches(4.35)
    box(s, cx - Inches(0.85), hold_y, Inches(1.70), Inches(0.40), "HOLD  (no trade)",
        size=8.5, shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=RGBColor(0xF6, 0xEC, 0xEC))
    line(s, cx, d1y + Inches(0.62), cx, hold_y)
    label(s, Inches(1.28), Inches(4.02), "[no]", size=8, w=Inches(0.8))
    line(s, d2x, d1y + Inches(0.62), d2x, Inches(4.55))
    line(s, d2x, Inches(4.55), cx + Inches(0.85), Inches(4.55), arrow=True)
    label(s, Inches(4.35), Inches(4.02), "[no]", size=8, w=Inches(0.8))

    box(s, Inches(6.70), Inches(2.62), Inches(2.45), Inches(0.42),
        "Size position, set SL / TP", size=8.5,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
    box(s, Inches(6.70), Inches(1.95), Inches(2.45), Inches(0.42),
        "Place order via ExecutionHandler", size=8.5,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
    line(s, d2x + Inches(0.62), d1y + Inches(0.31), Inches(7.92), Inches(3.04))
    label(s, Inches(6.25), Inches(3.30), "[yes]", size=8, w=Inches(0.8))
    line(s, Inches(7.92), Inches(2.62), Inches(7.92), Inches(2.37))

    box(s, Inches(7.80), Inches(1.32), Inches(0.24), Inches(0.24), "",
        shape=MSO_SHAPE.DONUT, fill=INK, line=INK)
    line(s, Inches(7.92), Inches(1.95), Inches(7.92), Inches(1.56))

    caption(s, f"Figure {next_fig()}: Activity Diagram of one decision cycle "
               f"(the hybrid AND-gate)")
    notes(s, "This is the heart of the system. Both guards must be true; either [no] "
             "branch merges to HOLD. Note the strict greater-than on both thresholds.")


def s_class(prs):
    s = add_slide(prs, "Design Specification — Class Diagram")
    y0 = Inches(1.08)
    class_box(s, Inches(0.42), y0, Inches(2.05), "DataHandler",
              ["- cache_dir: Path"],
              ["+ get_data(pair, tf)", "+ get_all()"])
    class_box(s, Inches(2.72), y0, Inches(2.20), "Preprocessor",
              ["- zscore_window: int", "- label_method: str"],
              ["+ transform(df)", "+ add_zscores(df)", "+ chronological_split()"])
    class_box(s, Inches(5.17), y0, Inches(2.05), "MLModel",
              ["- model: RandomForest"],
              ["+ tune(X, y)", "+ predict_proba(X)", "+ save() / load()"])
    class_box(s, Inches(7.47), y0, Inches(2.10), "SignalGenerator",
              ["- volume_threshold", "- confidence_threshold"],
              ["+ decide(p, z) : Signal"])

    y1 = Inches(2.58)
    class_box(s, Inches(0.42), y1, Inches(2.05), "RiskManager",
              ["- equity: float", "- risk_fraction: float"],
              ["+ size_position(...)", "+ can_trade()"])
    class_box(s, Inches(2.72), y1, Inches(2.20), "Backtester",
              ["- symbol: str"],
              ["+ run(df, probs)", "+ metrics()"])

    ax, ay, aw = Inches(5.60), Inches(2.58), Inches(2.45)
    a_bottom = class_box(s, ax, ay, aw, "«abstract»  ExecutionHandler", [],
                         ["+ connect()", "+ place_order(...)", "+ get_open_positions()",
                          "+ close_position(ticket)"], italic_name=True)

    subs = [
        (Inches(4.28), "MockExecution\nHandler"),
        (Inches(6.05), "MT5Execution\nHandler"),
        (Inches(7.82), "RemoteMT5\nExecutionHandler"),
    ]
    sub_top = Inches(4.42)
    for x, name in subs:
        box(s, x, sub_top, Inches(1.62), Inches(0.46), name, size=8, fill=LIGHT)
        generalization(s, x + Inches(0.81), sub_top, ax + aw / 2, a_bottom)

    line(s, Inches(2.47), Inches(1.45), Inches(2.72), Inches(1.45), arrow=False)
    line(s, Inches(4.92), Inches(1.45), Inches(5.17), Inches(1.45), arrow=False)
    line(s, Inches(7.22), Inches(1.45), Inches(7.47), Inches(1.45), arrow=False)
    line(s, Inches(3.80), Inches(2.58), Inches(3.80), Inches(2.18), arrow=False)

    caption(s, f"Figure {next_fig()}: Class Diagram. The engine depends only on the "
               f"abstract ExecutionHandler — never on a concrete broker.")
    notes(s, "The generalization triangles point at the abstract class. This is the "
             "design decision that let the whole system be built and tested on macOS "
             "while the real broker library is Windows-only.")


# --------------------------------------------------------------------------- #
# Implementation & results
# --------------------------------------------------------------------------- #
def s_hybrid(prs):
    s = add_slide(prs, "How a Trade Is Actually Decided")
    textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.3),
            "A worked example from a real run (EUR/USD, 1-hour candle):", size=12)
    data = [
        ["Check", "Value", "Threshold", "Result"],
        ["Rule gate — Volume Z-Score", "+4.249", "> +1.5", "PASS"],
        ["ML gate — P(bullish)", "0.567", "> 0.55", "PASS"],
        ["Decision", "BUY", "both must pass", "TRADE"],
    ]
    table(s, data, MARGIN, BODY_TOP + Inches(0.4), CONTENT_W, Inches(1.2),
          col_w=[Inches(3.3), Inches(1.9), Inches(1.9), Inches(2.0)], mark_cols=(3,))
    bullets(s, [
        "If either gate fails the system returns HOLD — and on roughly 98.7% of candles, "
        "that is exactly what happens.",
        "Both comparisons are strictly greater-than, so a borderline value does not trade.",
        "The position is then sized by the Risk Manager: 1% of equity at risk, stop-loss "
        "1.2% and take-profit 0.4% from entry, giving 14,532 units (0.15 lots) in this case.",
        "Every decision — including every HOLD — is logged with its probability and "
        "Z-Score, which is what makes the system auditable.",
    ], y=BODY_TOP + Inches(1.78), size=11.5, gap=5)
    notes(s, "These are genuine numbers from a dry run, not invented. If asked, the "
             "selectivity (1.3% of candles) is deliberate — see Barber & Odean.")


def s_label(prs):
    s = add_slide(prs, "The Decisive Design Decision: Triple-Barrier Labelling")
    bullets(s, [
        ("The problem:", 0, True),
        ("The first version asked the model 'will the next candle close higher?' — and "
         "it lost money on both pairs, because that question is not the one the strategy "
         "actually cares about.", 1),
        ("The fix (Lopez de Prado, 2018):", 0, True),
        ("Label each candle by what would really happen to a trade opened there: does "
         "price touch the take-profit before the stop-loss within 24 hours?", 1),
    ], size=12, gap=4, h=Inches(1.6))

    y = Inches(3.05)
    box(s, Inches(0.9), y - Inches(0.62), Inches(3.4), Inches(0.34),
        "upper barrier — take-profit  →  class 1", size=8.5, fill=RGBColor(0xEC, 0xF5, 0xEE))
    box(s, Inches(0.9), y + Inches(0.62), Inches(3.4), Inches(0.34),
        "lower barrier — stop-loss  →  class 0", size=8.5, fill=RGBColor(0xF6, 0xEC, 0xEC))
    box(s, Inches(4.55), y, Inches(1.5), Inches(0.34),
        "vertical barrier\n24 bars", size=8, fill=LIGHT)
    line(s, Inches(0.9), y + Inches(0.17), Inches(4.5), y + Inches(0.17), arrow=True)
    label(s, Inches(1.9), y + Inches(0.2), "time →", size=8)

    textbox(s, Inches(6.35), Inches(2.35), Inches(3.2), Inches(1.4),
            "Result: both pairs moved from\na net loss to a net profit.\n\n"
            "This single change mattered more\nthan every indicator tested.",
            size=11, bold=True, color=NAVY)
    notes(s, "If you are asked 'what was your biggest contribution?', this is the answer: "
             "changing the question the model is asked, so the training target matches "
             "how a trade actually resolves.")


def s_results(prs):
    s = add_slide(prs, "Results — Held-Out Test Set, Costs Included")
    textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.3),
            "Test period 20 January – 12 June 2026 (2,456 hourly candles, never seen "
            "during training):", size=11.5)
    data = [
        ["Metric", "Target", "EUR/USD", "GBP/USD"],
        ["Win rate", "> 60%", "73.3%  PASS", "78.4%  PASS"],
        ["95% confidence interval", "—", "[55.6% – 85.8%]", "[62.8% – 88.6%]"],
        ["Profit factor", "> 1.5", "1.34  FAIL", "1.62  PASS"],
        ["Maximum drawdown", "< 15%", "1.5%  PASS", "2.5%  PASS"],
        ["Sharpe (per-trade)", "> 1.0", "0.13  FAIL", "0.22  FAIL"],
        ["Net profit / trades", "—", "+$256.57  (30)", "+$531.82  (37)"],
        ["Targets met", "—", "2 of 4", "3 of 4"],
    ]
    table(s, data, MARGIN, BODY_TOP + Inches(0.42), CONTENT_W, Inches(2.6),
          col_w=[Inches(2.9), Inches(1.5), Inches(2.35), Inches(2.35)], mark_cols=(2, 3))
    textbox(s, MARGIN, BODY_TOP + Inches(3.15), CONTENT_W, Inches(0.5),
            "Sharpe is reported per-trade and unannualised; the > 1.0 benchmark is "
            "conventionally an annualised figure, so the two are not directly comparable. "
            "This is stated as a limitation rather than adjusted.", size=9.5, italic=True,
            color=RGBColor(0x55, 0x55, 0x55))
    notes(s, "Do not hide the two FAILs — lead with them if necessary. A panel trusts a "
             "candidate who reports failures precisely far more than one whose every "
             "number passes.")


def s_honesty(prs):
    s = add_slide(prs, "Results — How Much of This Is Actually the Model?")
    bullets(s, [
        ("A win rate alone can be manufactured by exit geometry.", 0, True),
        ("With a stop-loss three times wider than the take-profit, most trades close as "
         "small wins. To test this, the same exits were run with a RANDOM trade "
         "direction: that baseline wins 67–69%.", 1),
        ("So the 73–78% headline win rate is mostly geometry, not prediction.", 1),
        ("Where the model's edge does show:", 0, True),
        ("Profit factor. Against every random-direction seed, the trained model wins on "
         "profit factor — the metric that measures whether the trades KEPT were better "
         "than the trades SKIPPED.", 1),
        ("Remaining honest caveats:", 0, True),
        ("Only ~30 trades per pair, hence the wide confidence intervals.", 1),
        ("The training label is long-only with a 24-bar horizon, while live trades take "
         "both directions and are held to their barriers — a documented inconsistency.", 1),
        ("Execution latency was measured only on a demo account, not at scale.", 1),
    ], size=11.5, gap=4)
    notes(s, "This slide wins vivas. You raised the objection before the panel did, "
             "quantified it, and showed where the model still adds value.")


def s_negative(prs):
    s = add_slide(prs, "Results — Six Measured Negative Results")
    textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.3),
            "Each feature was added alone, retrained, and measured on both pairs. None "
            "improved both, so all are switched off — with the code kept.", size=11)
    data = [
        ["Feature tested", "In the literature?", "Measured outcome"],
        ["RSI", "Yes (Chong et al.)", "Hurt both pairs"],
        ["MACD", "Yes (Chong et al.)", "Hurt badly — drawdown above 15%"],
        ["ATR (feature and stops)", "No", "Neutral to harmful"],
        ["Higher-timeframe trend", "No", "Helped EUR/USD, hurt GBP/USD"],
        ["Time-of-day / session", "No", "Helped EUR/USD, hurt GBP/USD"],
        ["Order blocks (SMC zones)", "Yes (Sirignano & Cont)",
         "Helped GBP/USD only — 1 of 4 configurations"],
    ]
    table(s, data, MARGIN, BODY_TOP + Inches(0.42), CONTENT_W, Inches(2.3),
          col_w=[Inches(3.0), Inches(2.4), Inches(3.7)])
    textbox(s, MARGIN, BODY_TOP + Inches(2.85), CONTENT_W, Inches(0.55),
            "Reporting these is a deliberate contribution: the widely-taught indicators "
            "did not generalise across two closely related currency pairs, which is "
            "evidence about the method, not a failure of it.",
            size=10.5, italic=True, color=NAVY)
    notes(s, "Frame this as publishable. Most student projects report only what worked; "
             "you can state precisely what did not, and by how much.")


def s_orderblocks(prs):
    s = add_slide(prs, "Case Study — Order Blocks, Tested Properly")
    bullets(s, [
        ("Order blocks are the core of the sibling live product, so the concept was "
         "implemented here and measured rather than asserted.", 0),
        ("A zone is created when a candle CLOSES beyond the recent swing (a break of "
         "structure, not a wick), filtered by ATR size, and consumed when price trades "
         "back into it. The model receives distance-to-zone and an inside-zone flag.", 1),
    ], size=11.5, h=Inches(1.15), gap=4)
    data = [
        ["Configuration", "Pair", "Win rate", "Profit factor", "Verdict"],
        ["Default exits", "EUR/USD", "73.3% → 71.0%", "1.34 → 1.21", "worse"],
        ["Default exits", "GBP/USD", "78.4% → 79.1%", "1.62 → 1.77", "better"],
        ["Far take-profit", "EUR/USD", "36.8% → 30.0%", "1.42 → 1.09", "worse"],
        ["Far take-profit", "GBP/USD", "50.0% → 36.8%", "2.42 → 1.78", "worse"],
    ]
    table(s, data, MARGIN, BODY_TOP + Inches(1.20), CONTENT_W, Inches(1.5),
          col_w=[Inches(2.2), Inches(1.35), Inches(2.0), Inches(2.0), Inches(1.55)])
    bullets(s, [
        ("The model DID use them — the order-block features carry about 20% of total "
         "feature importance. This was not an ignored input.", 0),
        ("But the textbook part was the useless part: the 'price is inside a zone' flag "
         "scored 0.001 importance, because price is inside a live zone on only 3.5% of "
         "candles. What the model used was proximity, not the zone as a trigger.", 0),
    ], y=BODY_TOP + Inches(2.85), size=11, gap=4)
    notes(s, "This is your strongest single slide for demonstrating research method: a "
             "popular technique, implemented faithfully, measured, and rejected on "
             "evidence — with an explanation of WHY it failed.")


def s_proof_backtest(prs):
    s = add_slide(prs, "Evidence — Backtest Run and Dashboard")
    placeholder(s, MARGIN, BODY_TOP + Inches(0.05), Inches(4.4), Inches(3.05),
                "Terminal output of:\nscripts/run_backtest.py EURUSD 1h\n\n"
                "Show the metrics block and the PASS/FAIL lines against targets.")
    placeholder(s, Inches(5.15), BODY_TOP + Inches(0.05), Inches(4.4), Inches(3.05),
                "Streamlit dashboard at localhost:8501\n\n"
                "Show the metric cards, the equity curve and the trade table.")
    caption(s, "Figure {}: Reproducible backtest output (left) and the monitoring "
               "dashboard (right)".format(next_fig()))
    notes(s, "Have both of these open in a terminal and a browser tab during the defence "
             "in case the panel asks you to run it live. Commands are in docs/COMMANDS.md.")


def s_deployment(prs):
    s = add_slide(prs, "Deployment — A Documented Engineering Finding")
    bullets(s, [
        ("The plan was to run MetaTrader 5 headless in a Linux Docker container under Wine.",
         0, True),
        ("It cannot work. MetaTrader's Python API fails to initialise under Wine with "
         "error -10005 (an inter-process communication timeout) — reproduced across three "
         "environments, including native x86 with no emulation, and including a "
         "byte-for-byte copy of a published working reference.", 1),
        ("The resolution:", 0, True),
        ("A native Windows host runs the terminal and a small RPC service; the analytical "
         "engine runs unchanged on macOS or Linux and reaches it over TCP. On Windows the "
         "same API initialises on the first attempt.", 1),
        ("Why this belongs in the report:", 0, True),
        ("It is a negative engineering result with a clear cause, a reproduction, and a "
         "working alternative — and it is exactly the kind of finding that saves the next "
         "person weeks.", 1),
    ], size=11.5, gap=4, h=Inches(2.5))

    y = Inches(3.75)
    box(s, Inches(0.55), y, Inches(2.2), Inches(0.55), "Engine\n(macOS / Linux)", size=8.5,
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
    box(s, Inches(3.45), y, Inches(2.2), Inches(0.55), "RPC Service\n(Windows host)",
        size=8.5, shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
    box(s, Inches(6.35), y, Inches(2.2), Inches(0.55), "MetaTrader 5\n(demo account)",
        size=8.5, shape=MSO_SHAPE.ROUNDED_RECTANGLE, fill=LIGHT)
    line(s, Inches(2.75), y + Inches(0.27), Inches(3.45), y + Inches(0.27), back_arrow=True)
    line(s, Inches(5.65), y + Inches(0.27), Inches(6.35), y + Inches(0.27), back_arrow=True)
    label(s, Inches(2.65), y - Inches(0.2), "JSON over TCP", size=7.5, w=Inches(0.9))
    notes(s, "Say 'negative result' with confidence. You proved a published approach does "
             "not work and documented why — that is a contribution.")


def s_gadel(prs):
    s = add_slide(prs, "From Research to a Live Product")
    textbox(s, MARGIN, BODY_TOP, CONTENT_W, Inches(0.35),
            "The execution architecture developed in this research is the same "
            "architecture now running in a live production trading system (Gadel).",
            size=12, bold=True, color=NAVY)

    for x, title, rows, tint in (
        (MARGIN, "THIS PROJECT  (research)",
         ["Streamlit dashboard", "Signal Generator (Z-Score AND Random Forest)",
          "Risk Manager", "▸ Abstract ExecutionHandler ◂", "▸ RPC service ◂",
          "MetaTrader 5  (demo)"], LIGHT),
        (Inches(5.15), "GADEL  (live production)",
         ["Web dashboard", "MQL5 Expert Advisor (EMA cross AND order blocks)",
          "Risk / position manager", "▸ Abstract execution layer ◂", "▸ RPC service ◂",
          "MetaTrader 5  (live)"], RGBColor(0xF4, 0xF0, 0xE8)),
    ):
        box(s, x, BODY_TOP + Inches(0.48), Inches(4.4), Inches(0.32), title,
            size=10, bold=True, fill=NAVY, line=NAVY, color=WHITE)
        y = BODY_TOP + Inches(0.88)
        for i, r in enumerate(rows):
            shared = r.startswith("▸")
            box(s, x, y, Inches(4.4), Inches(0.36), r.replace("▸", "").replace("◂", "").strip(),
                size=8.5, fill=ACCENT if shared else tint,
                bold=shared, line=NAVY if shared else INK, line_w=1.5 if shared else 1.0)
            if i < len(rows) - 1:
                line(s, x + Inches(2.2), y + Inches(0.36), x + Inches(2.2), y + Inches(0.42),
                     arrow=False, color=GREY)
            y += Inches(0.42)

    textbox(s, MARGIN, Inches(4.72), CONTENT_W, Inches(0.4),
            "Shared (highlighted): the abstract execution interface and the RPC boundary — "
            "the two components this research designed and proved.",
            size=9.5, italic=True, color=NAVY, align=PP_ALIGN.CENTER)
    caption(s, f"Figure {next_fig()}: Architectural correspondence between the research "
               f"system and the live product", y=H - Inches(0.34))
    notes(s, "Be precise about the direction of transfer: the ARCHITECTURE and the Wine "
             "finding transferred. Gadel contains no machine learning and has never run "
             "this project's model — do not claim its trading results as yours.")


def s_gadel_honest(prs):
    s = add_slide(prs, "What the Live Product Does and Does Not Prove")
    for x, head, items, tint, col in (
        (MARGIN, "IT SUPPORTS", [
            "That the execution architecture works in production, under real conditions.",
            "That Wine is a dead end and native Windows is the correct deployment route.",
            "Five defects in this project's live-order path that only real trading "
            "exposes — fill modes, thread affinity, magic numbers, lot rounding, "
            "whitespace in server names — all since fixed here.",
        ], RGBColor(0xEC, 0xF5, 0xEE), GOOD),
        (Inches(5.15), "IT DOES NOT SUPPORT", [
            "Any trading claim in this report. It contains NO machine learning — "
            "verified by a repository-wide search.",
            "It trades gold on hand-written rules; it has never run this project's "
            "model, volume gate, labelling method, currency pairs or timeframe.",
            "Therefore the win rate, profit factor, drawdown and Sharpe in this report "
            "remain backtested results — which is an honest and defensible basis.",
        ], RGBColor(0xF6, 0xEC, 0xEC), BAD),
    ):
        box(s, x, BODY_TOP + Inches(0.05), Inches(4.4), Inches(0.34), head,
            size=10.5, bold=True, fill=col, line=col, color=WHITE)
        tb = s.shapes.add_textbox(x + Inches(0.12), BODY_TOP + Inches(0.52),
                                  Inches(4.15), Inches(2.6))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, it in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(8)
            r = p.add_run()
            r.text = "•  " + it
            _style_run(r, 10)
    textbox(s, MARGIN, Inches(4.35), CONTENT_W, Inches(0.7),
            "Defensible statement: \"The Linux/Wine deployment route was shown to be "
            "unworkable, and the native-Windows route was verified end to end in a "
            "sibling production deployment using the same execution architecture. The "
            "strategy results reported here are obtained by backtesting on held-out data "
            "with modelled transaction costs.\"",
            size=10, italic=True, color=NAVY)
    notes(s, "Rehearse this slide. If a panel member suspects you are borrowing another "
             "system's results, this slide answers it before they finish the question.")


def s_proof_gadel(prs):
    s = add_slide(prs, "Evidence — The Live Deployment")
    placeholder(s, MARGIN, BODY_TOP + Inches(0.05), Inches(4.4), Inches(3.05),
                "MetaTrader 5 on the Windows host:\nTrade / History tab showing positions "
                "placed by this system\n\nREDACT: account number, balance, server name")
    placeholder(s, Inches(5.15), BODY_TOP + Inches(0.05), Inches(4.4), Inches(3.05),
                "Gadel dashboard or terminal\nshowing the shared execution layer running "
                "in production\n\nREDACT: account numbers, balances, API keys")
    caption(s, f"Figure {next_fig()}: Live execution evidence (identifying details redacted)")
    notes(s, "Redaction is not optional — these are real accounts. Black boxes over "
             "account numbers, balances, server hostnames and any token.")


def s_impact(prs):
    s = add_slide(prs, "Relevance and Potential Impact")
    bullets(s, [
        ("Who benefits:", 0, True),
        ("Retail traders, who gain consistent rule execution and enforced risk limits "
         "instead of emotional decisions.", 1),
        ("Students and researchers, who gain a fully reproducible evaluation method — "
         "every number in this project has a command that regenerates it.", 1),
        ("Practitioners, who gain a documented negative result on deployment and on five "
         "widely-taught indicators.", 1),
        ("Evidence of demand:", 0, True),
    ], size=11.5, h=Inches(1.9), gap=4)
    placeholder(s, MARGIN, BODY_TOP + Inches(1.95), Inches(4.3), Inches(1.9),
                "Gadel waiting-list registrations\n\nShow the count and the signup list "
                "(REDACT names and email addresses)")
    bullets(s, [
        ("Over 30 registrations on the live product's waiting list, with no paid "
         "advertising.", 0),
        ("This is expressed interest, not revenue — and is described as such.", 0),
        ("The academic contribution stands independently of any commercial outcome.", 0),
    ], x=Inches(5.0), y=BODY_TOP + Inches(1.95), w=Inches(4.55), size=10.5, gap=5)
    notes(s, "Say 'expressed interest', never 'customers' or 'willing to pay' — a "
             "waiting-list signup is not a purchase. Overstating this is the one thing "
             "that could damage your credibility on an otherwise careful project.")


def s_contribution(prs):
    s = add_slide(prs, "Contribution to Knowledge")
    bullets(s, [
        "A hybrid decision architecture in which a statistical volume filter and a "
        "Random Forest must agree, giving every trade both a statistical reason and a "
        "model probability — a directly auditable design.",
        "Empirical evidence that triple-barrier labelling — aligning the training target "
        "with how a trade actually closes — is more consequential than any indicator "
        "tested here, turning both pairs from loss to profit.",
        "Six documented negative results: RSI, MACD, ATR, higher-timeframe trend, "
        "time-of-day and order blocks each failed to generalise across two closely "
        "related currency pairs.",
        "A demonstration that a headline win rate can be produced by exit geometry alone, "
        "with a no-skill baseline showing how to separate geometry from genuine skill — "
        "a method other studies can reuse.",
        "A reproducible, costed evaluation protocol: sealed chronological test set, "
        "confidence intervals on every rate, and a published command for every number.",
        "A documented deployment finding: MetaTrader 5's Python API cannot initialise "
        "under Wine, with the working native-Windows alternative and its architecture.",
    ], size=11.5, gap=5)
    notes(s, "Six contributions, and four of them are about method rather than "
             "performance. That is the right emphasis for a Computer Science degree.")


def s_undone(prs):
    s = add_slide(prs, "Work Left Undone")
    bullets(s, [
        ("In progress:", 0, True),
        ("A live execution session on a broker demo account, running on a Windows host, "
         "to record signal-to-fill latency against the 500 ms target. The system and the "
         "protocol are complete; the session needs calendar time because the volume gate "
         "fires roughly once or twice per pair per week.", 1),
        ("Remaining:", 0, True),
        ("Chapters 4 and 5 of the report — the measured material and figures already "
         "exist in the project documentation.", 1),
        ("Applying the documented factual corrections to Chapters 1–3.", 1),
        ("Identified for future work:", 0, True),
        ("Aligning the training label fully with the executed trade, most likely through "
         "separate long-side and short-side models.", 1),
        ("Meta-labelling — a second model deciding whether to accept each primary "
         "signal — the standard route to raising precision at fixed risk-reward.", 1),
        ("Extending beyond two pairs and one timeframe to test generalisation properly.", 1),
    ], size=11.5, gap=4)
    notes(s, "Being specific about what is unfinished, and why, reads as control. The "
             "latency session is limited by market conditions, not by unfinished code.")


def s_conclusion(prs):
    s = add_slide(prs, "Conclusion")
    bullets(s, [
        "A complete automated trading system was designed, implemented and evaluated: "
        "13 modules, 231 automated tests, a dashboard, a containerised deployment and a "
        "live broker execution path.",
        "On held-out data with transaction costs charged, it meets the win-rate and "
        "drawdown targets on both currency pairs and the profit-factor target on one; "
        "the Sharpe target is not met, and that is reported rather than adjusted away.",
        "The most valuable outcomes are methodological: the labelling insight, the "
        "no-skill baseline that separates exit geometry from genuine skill, and six "
        "negative results reported in full.",
        "The execution architecture designed here is already running in a live production "
        "system, while the trading results reported remain, correctly, backtested results.",
        ("Every claim in this presentation is reproducible from the project repository "
         "with a single documented command.", 0, True),
    ], size=12, gap=7)
    notes(s, "Close on the last bullet and stop talking. It is the strongest sentence you "
             "have and it invites exactly the questions you are prepared for.")


def s_references(prs, rows, part):
    s = add_slide(prs, f"References ({part})")
    tb = s.shapes.add_textbox(MARGIN, BODY_TOP + Inches(0.05), CONTENT_W, Inches(3.9))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, r in enumerate(rows):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(9)
        run = p.add_run()
        run.text = r
        _style_run(run, 10)
    notes(s, "Do not read these aloud. They are here so the panel can see the work is "
             "grounded in the literature; the full list is in the report.")
    return s


def s_refs(prs):
    s_references(prs, [
        "Bailey, D.H., Borwein, J., Lopez de Prado, M. and Zhu, Q.J. (2014). "
        "\"Pseudo-mathematics and financial charlatanism: the effects of backtest "
        "overfitting on out-of-sample performance\". Notices of the AMS, 61(5), pp. 458–471.",
        "Barber, B.M. and Odean, T. (2000). \"Trading is hazardous to your wealth: the "
        "common stock investment performance of individual investors\". Journal of "
        "Finance, 55(2), pp. 773–806.",
        "Chong, E., Han, C. and Park, F.C. (2017). \"Deep learning networks for stock "
        "market analysis and prediction\". Expert Systems with Applications, 83, pp. 187–205.",
        "European Securities and Markets Authority (2018). Product Intervention Measures "
        "relating to Contracts for Differences. ESMA35-43-1135.",
        "Hu, Z., Zhao, Y. and Khushi, M. (2021). \"A survey of forex and stock price "
        "prediction using deep learning\". Applied System Innovation, 4(1), 9.",
    ], "1 of 2")
    s_references(prs, [
        "Lopez de Prado, M. (2018). Advances in Financial Machine Learning. Hoboken, "
        "New Jersey: John Wiley & Sons.",
        "Pedregosa, F. et al. (2011). \"Scikit-learn: machine learning in Python\". "
        "Journal of Machine Learning Research, 12, pp. 2825–2830.",
        "Sirignano, J. and Cont, R. (2019). \"Universal features of price formation in "
        "financial markets: perspectives from deep learning\". Quantitative Finance, "
        "19(9), pp. 1449–1459.",
        "Wilson, E.B. (1927). \"Probable inference, the law of succession, and "
        "statistical inference\". Journal of the American Statistical Association, "
        "22(158), pp. 209–212.",
        "Yildirim, D.C., Toroslu, I.H. and Fiore, U. (2021). \"Forecasting directional "
        "movement of Forex data using LSTM with technical and macroeconomic indicators\". "
        "Financial Innovation, 7(1), 1.",
    ], "2 of 2")


def s_thanks(prs):
    s = add_slide(prs, number=False)
    box(s, Emu(0), Emu(0), W, Inches(0.12), "", fill=NAVY, line=NAVY)
    textbox(s, MARGIN, Inches(2.15), CONTENT_W, Inches(0.6), "Thank You",
            size=34, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    textbox(s, MARGIN, Inches(2.95), CONTENT_W, Inches(0.4),
            "Questions are welcome.", size=14, color=RGBColor(0x55, 0x55, 0x55),
            align=PP_ALIGN.CENTER)
    textbox(s, MARGIN, Inches(3.75), CONTENT_W, Inches(0.5),
            "AWOSUSI GABRIEL AYOMIDE   •   CSC/2019/079   •   CSC 504",
            size=11, color=GREY, align=PP_ALIGN.CENTER)
    notes(s, "Have docs/DEFENCE_GUIDE.md open on a second screen — it holds prepared "
             "answers to the twelve most likely questions.")


def _validate(path: Path) -> None:
    """Fail loudly if the saved file would be rejected by a strict reader.

    Two defects have already shipped from this script. Both were invisible in
    PowerPoint but fatal in Keynote and Google Slides:

      1. Float coordinates (``y="1792224.0"``). ``w / 2`` returns a float in Python 3
         and python-pptx writes it verbatim, but ST_Coordinate is an integer type.
      2. A stale ``sldSz type="screen4x3"`` on a 16:9 deck.

    An earlier version of this check wrapped the shape reads in
    ``except Exception: continue``, which silently swallowed (1) and reported a clean
    file. This one is deliberately allowed to raise.
    """
    import re
    import zipfile

    with zipfile.ZipFile(path) as z:
        float_attr = re.compile(r'\b(x|y|cx|cy|w|h)="(-?\d+\.\d+)"')
        offenders = [
            f"{name}: {attr}={val}"
            for name in z.namelist()
            if name.startswith("ppt/slides/") and name.endswith(".xml")
            for attr, val in float_attr.findall(z.read(name).decode("utf-8", "ignore"))
        ]
        if offenders:
            raise ValueError(
                f"{len(offenders)} non-integer coordinate(s): {offenders[:5]}"
            )
        sld_sz = re.search(
            r"<p:sldSz[^/]*/>", z.read("ppt/presentation.xml").decode("utf-8")
        )
    if sld_sz and "type=" in sld_sz.group(0):
        raise ValueError(f"sldSz still declares a size type: {sld_sz.group(0)}")

    # Speaker notes are the rehearsal script; losing them would ship a worse deck
    # silently. They are also the reason the base template exists.
    with zipfile.ZipFile(path) as z:
        n_notes = sum(1 for n in z.namelist()
                      if n.startswith("ppt/notesSlides/notesSlide"))
    if n_notes == 0:
        raise ValueError("saved deck contains no speaker notes")

    # Touch every coordinate so an unparsable value raises instead of being skipped.
    for slide in Presentation(str(path)).slides:
        for shape in slide.shapes:
            _ = (shape.left, shape.top, shape.width, shape.height)


# --------------------------------------------------------------------------- #
def build() -> Path:
    prs = _base_presentation()
    _set_slide_size(prs, W, H)

    s_title(prs)
    s_outline(prs)
    s_intro1(prs)
    s_intro2(prs)
    s_problem(prs)
    s_aim(prs)
    s_lit1(prs)
    s_lit2(prs)
    s_methodology(prs)
    s_justification(prs)
    s_scope(prs)
    s_workdone_overview(prs)
    s_context(prs)
    s_architecture(prs)
    s_block(prs)
    s_usecase(prs)
    s_activity(prs)
    s_class(prs)
    s_hybrid(prs)
    s_label(prs)
    s_results(prs)
    s_honesty(prs)
    s_negative(prs)
    s_orderblocks(prs)
    s_proof_backtest(prs)
    s_deployment(prs)
    s_gadel(prs)
    s_gadel_honest(prs)
    s_proof_gadel(prs)
    s_impact(prs)
    s_contribution(prs)
    s_undone(prs)
    s_conclusion(prs)
    s_refs(prs)
    s_thanks(prs)

    OUT.parent.mkdir(exist_ok=True)
    prs.save(str(OUT))
    _validate(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path.relative_to(ROOT)}")
    print(f"Figures numbered 1..{_fig['n']}")
