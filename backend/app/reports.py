"""Generate Word (.docx) and PowerPoint (.pptx) reports from a summary dict."""
from __future__ import annotations

import io
from datetime import date

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from pptx import Presentation
from pptx.dml.color import RGBColor as PptColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches as PInches, Pt as PPt

from . import charts
from .analytics import format_inr

ACCENT = RGBColor(0x3B, 0x5B, 0xDB)
INK = RGBColor(0x1F, 0x29, 0x33)
MUTED = RGBColor(0x6B, 0x72, 0x80)


def inr(x: float | None) -> str:
    return format_inr(x)


def _period(totals: dict) -> str:
    fmt = lambda d: date.fromisoformat(d).strftime("%d %b %Y")  # noqa: E731
    return f"{fmt(totals['period_start'])} – {fmt(totals['period_end'])}"


def _kpis(totals: dict) -> list[tuple[str, str]]:
    rate = totals.get("savings_rate")
    return [
        ("Income", inr(totals["income"])),
        ("Spending", inr(totals["spend"])),
        ("Invested", inr(totals["invested"])),
        ("Savings rate", f"{rate}%" if rate is not None else "–"),
    ]


# --------------------------------------------------------------------------- Word

def _shade(cell, hex_fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _table(doc, headers: list[str], rows: list[list[str]], widths: list[float], right_cols=()):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.bold, run.font.size, run.font.color.rgb = True, Pt(9.5), RGBColor(0xFF, 0xFF, 0xFF)
        _shade(cell, "3B5BDB")
    for r_i, row in enumerate(rows):
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            run = p.add_run(str(value))
            run.font.size = Pt(9.5)
            if i in right_cols:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if r_i % 2:
                _shade(cells[i], "F1F3F9")
    _set_widths(table, widths)
    doc.add_paragraph()
    return table


def _set_widths(table, widths: list[float]):
    """Fixed column widths that both Word and LibreOffice respect (cell widths + table grid)."""
    table.autofit = False
    grid = table._tbl.tblGrid
    for i, w in enumerate(widths):
        grid.gridCol_lst[i].w = Inches(w)
        for row in table.rows:
            row.cells[i].width = Inches(w)


def _heading(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run(text)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(14), ACCENT


def build_docx(summary: dict, title: str = "SpendSense Expense Report") -> bytes:
    totals = summary["totals"]
    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Inches(0.9)
    section.top_margin = section.bottom_margin = Inches(0.8)
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(10.5)

    p = doc.add_paragraph()
    run = p.add_run(title)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(22), INK
    p = doc.add_paragraph()
    run = p.add_run(f"{_period(totals)}  ·  {totals['transactions']} transactions  ·  "
                    f"generated {date.today():%d %b %Y}")
    run.font.size, run.font.color.rgb = Pt(10), MUTED

    # KPI strip
    kpis = _kpis(totals)
    table = doc.add_table(rows=2, cols=len(kpis))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (label, value) in enumerate(kpis):
        top, bottom = table.rows[0].cells[i], table.rows[1].cells[i]
        for c in (top, bottom):
            _shade(c, "F1F3F9")
        top.text = ""
        r = top.paragraphs[0].add_run(label.upper())
        r.font.size, r.font.color.rgb = Pt(8), MUTED
        bottom.text = ""
        r = bottom.paragraphs[0].add_run(value)
        r.bold, r.font.size, r.font.color.rgb = True, Pt(16), INK
    _set_widths(table, [6.7 / len(kpis)] * len(kpis))
    doc.add_paragraph()

    if summary["insights"]:
        _heading(doc, "Key insights")
        for line in summary["insights"]:
            doc.add_paragraph(line, style="List Bullet")

    _heading(doc, "Spending by category")
    doc.add_picture(io.BytesIO(charts.category_chart(summary["by_category"])), width=Inches(6.3))
    _table(doc, ["Category", "Amount", "Share", "Txns"],
           [[c["category"], inr(c["amount"]), f"{c['share']}%", c["count"]] for c in summary["by_category"]],
           [2.9, 1.4, 1.0, 0.9], right_cols=(1, 2, 3))

    _heading(doc, "Monthly income vs spending")
    doc.add_picture(io.BytesIO(charts.monthly_chart(summary["monthly"])), width=Inches(6.3))
    _table(doc, ["Month", "Income", "Spending", "Net"],
           [[m["label"], inr(m["income"]), inr(m["spend"]), inr(m["net"])] for m in summary["monthly"]],
           [1.6, 1.55, 1.55, 1.5], right_cols=(1, 2, 3))

    _heading(doc, "Top merchants")
    _table(doc, ["Merchant", "Amount", "Txns"],
           [[m["merchant"], inr(m["amount"]), m["count"]] for m in summary["top_merchants"]],
           [3.6, 1.6, 1.0], right_cols=(1, 2))

    if summary["recurring"]:
        _heading(doc, "Recurring payments")
        _table(doc, ["Merchant", "Category", "Typical amount", "Months seen"],
               [[r["merchant"], r["category"], inr(r["typical_amount"]), r["months"]] for r in summary["recurring"]],
               [2.2, 2.0, 1.3, 0.9], right_cols=(2, 3))

    _heading(doc, "Largest expenses")
    _table(doc, ["Date", "Merchant", "Category", "Amount"],
           [[e["date"], e["merchant"], e["category"], inr(e["amount"])] for e in summary["largest_expenses"]],
           [1.1, 2.2, 1.8, 1.2], right_cols=(3,))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- PowerPoint

P_ACCENT = PptColor(0x3B, 0x5B, 0xDB)
P_INK = PptColor(0x1F, 0x29, 0x33)
P_MUTED = PptColor(0x6B, 0x72, 0x80)
P_PANEL = PptColor(0xF1, 0xF3, 0xF9)
P_WHITE = PptColor(0xFF, 0xFF, 0xFF)


def _text(slide, left, top, width, height, text, size=14, bold=False, color=P_INK, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(PInches(left), PInches(top), PInches(width), PInches(height))
    tf = box.text_frame
    tf.word_wrap = True
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.size, run.font.bold, run.font.color.rgb = PPt(size), bold, color
        run.font.name = "Calibri"
        p.space_after = PPt(6)
    return box


def _slide_title(prs, title: str, subtitle: str | None = None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, PInches(0.18), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = P_ACCENT
    bar.line.fill.background()
    _text(slide, 0.6, 0.35, 12, 0.7, title, size=28, bold=True)
    if subtitle:
        _text(slide, 0.6, 1.0, 12, 0.4, subtitle, size=13, color=P_MUTED)
    return slide


def _ppt_table(slide, left, top, width, headers, rows, col_widths):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), PInches(left), PInches(top),
                                   PInches(width), PInches(0.38 * (len(rows) + 1)))
    table = shape.table
    for i, w in enumerate(col_widths):
        table.columns[i].width = PInches(w)
    for r in range(len(rows) + 1):
        for c in range(len(headers)):
            cell = table.cell(r, c)
            cell.text = str(headers[c] if r == 0 else rows[r - 1][c])
            para = cell.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.RIGHT if c > 0 else PP_ALIGN.LEFT
            font = para.runs[0].font
            font.size, font.name = PPt(12), "Calibri"
            font.bold = r == 0
            font.color.rgb = P_WHITE if r == 0 else P_INK
            cell.fill.solid()
            cell.fill.fore_color.rgb = P_ACCENT if r == 0 else (P_PANEL if r % 2 == 0 else P_WHITE)


def build_pptx(summary: dict, title: str = "SpendSense Expense Report") -> bytes:
    totals = summary["totals"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = PInches(13.333), PInches(7.5)

    # 1. Title
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = P_ACCENT
    bg.line.fill.background()
    _text(slide, 0.9, 2.6, 11.5, 1.2, title, size=44, bold=True, color=P_WHITE)
    _text(slide, 0.9, 3.8, 11.5, 0.6, f"{_period(totals)}  ·  {totals['transactions']} transactions",
          size=18, color=PptColor(0xDB, 0xE4, 0xFF))

    # 2. Overview: KPI cards + insights
    slide = _slide_title(prs, "Overview", _period(totals))
    for i, (label, value) in enumerate(_kpis(totals)):
        left = 0.6 + i * 3.08
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, PInches(left), PInches(1.7),
                                      PInches(2.85), PInches(1.45))
        card.adjustments[0] = 0.08
        card.fill.solid()
        card.fill.fore_color.rgb = P_PANEL
        card.line.fill.background()
        _text(slide, left + 0.25, 1.85, 2.4, 0.4, label.upper(), size=11, color=P_MUTED)
        _text(slide, left + 0.25, 2.25, 2.4, 0.7, value, size=28, bold=True)
    _text(slide, 0.6, 3.6, 12, 0.5, "Key insights", size=18, bold=True, color=P_ACCENT)
    _text(slide, 0.6, 4.15, 12, 3, [f"•  {s}" for s in summary["insights"]] or ["No insights yet."], size=15)

    # 3. Category chart
    slide = _slide_title(prs, "Where the money went", "Spending by category (transfers and investments excluded)")
    pic = charts.category_chart(summary["by_category"], width=9)
    slide.shapes.add_picture(io.BytesIO(pic), PInches(0.6), PInches(1.6), height=PInches(5.4))

    # 4. Monthly trend
    slide = _slide_title(prs, "Monthly income vs spending")
    pic = charts.monthly_chart(summary["monthly"], width=11)
    slide.shapes.add_picture(io.BytesIO(pic), PInches(0.6), PInches(1.5), width=PInches(12))

    # 5. Merchants + recurring
    slide = _slide_title(prs, "Top merchants & recurring payments")
    _ppt_table(slide, 0.6, 1.5, 6.0, ["Merchant", "Amount", "Txns"],
               [[m["merchant"], inr(m["amount"]), m["count"]] for m in summary["top_merchants"]],
               [3.4, 1.6, 1.0])
    if summary["recurring"]:
        _ppt_table(slide, 7.0, 1.5, 5.7, ["Recurring", "Typical", "Months"],
                   [[r["merchant"], inr(r["typical_amount"]), r["months"]] for r in summary["recurring"][:8]],
                   [3.1, 1.6, 1.0])
    else:
        _text(slide, 7.0, 1.5, 5.7, 1, "No recurring payments detected.", size=14, color=P_MUTED)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
