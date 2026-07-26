"""PDF report writer (§3) via ``reportlab`` (optional ``export`` extra).

``render_pdf_bytes(payload)`` for downloads; ``write_pdf(payload, path)`` for
filesystem writes. Uses only core PDF fonts (Helvetica) for OS portability.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from mypyskindose.safe_output import atomic_write_private

from .._format import (
    COLOR_ERROR,
    COLOR_WARNING,
    CORRECTION_HEADER,
    KERMA_METER_WEIGHTING_FOOTNOTE,
    OFFSET_LABELS,
    collect_alert_lines,
    correction_row,
    corrections_use_kerma_meter,
    dosimetric_rows,
)
from ..models import ExamSection, ExportPayload

_AMBER = colors.HexColor(f"#{COLOR_WARNING}")
_RED = colors.HexColor(f"#{COLOR_ERROR}")
_PAGE = A4
_MARGIN = 1.8 * cm
_CONTENT_WIDTH = _PAGE[0] - 2 * _MARGIN

_styles = getSampleStyleSheet()
_BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10)
_CELL = ParagraphStyle("cell", parent=_BODY, wordWrap="CJK")
_H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontName="Helvetica-Bold", fontSize=16)
_H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontName="Helvetica-Bold", fontSize=12)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas rendering a 'Page X of Y' footer.

    Pages are buffered on ``showPage``; the total count is known only at
    ``save``, when each buffered page is replayed with the footer drawn.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self) -> None:
        self._saved_states.append(dict(self.__dict__))
        self._startPage()  # type: ignore[attr-defined]

    def save(self) -> None:
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.grey)
        self.drawRightString(_PAGE[0] - _MARGIN, _MARGIN * 0.5, f"Page {self.getPageNumber()} of {total}")


def _p(text: str, style: ParagraphStyle = _CELL) -> Paragraph:
    return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def _table(rows: list[list], col_widths: list[float], *, header: bool = True) -> Table:
    data = [[_p(c) for c in row] for row in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")))
        style.append(("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t


def _alert_box(payload: ExportPayload) -> list:
    flow: list[Any] = [Paragraph("Executive alerts", _H2)]
    for text, severity in collect_alert_lines(payload):
        bg = _RED if severity == "error" else (_AMBER if severity == "warning" else colors.HexColor("#D4EDDA"))
        cell = Table([[_p(text, _BODY)]], colWidths=[_CONTENT_WIDTH])
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#B08800")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        flow.append(cell)
        flow.append(Spacer(1, 3))
    return flow


def _dosimetric_table(payload: ExportPayload) -> Table:
    rows = [["Metric", "Value"]] + dosimetric_rows(payload.cumulative.metrics)
    return _table(rows, [_CONTENT_WIDTH * 0.5, _CONTENT_WIDTH * 0.5])


def _settings_flow(exam: ExamSection, multi: bool) -> list:
    rows = [["Setting", "Value"]]
    for key, value in exam.settings.items():
        if key in ("phantom", "patient_offset"):
            continue
        rows.append([key, str(value)])
    for key, value in exam.settings.get("phantom", {}).items():
        rows.append([f"phantom.{key}", str(value)])
    for key, value in exam.settings.get("patient_offset", {}).items():
        rows.append([str(OFFSET_LABELS.get(key, key)), str(value)])
    rows.append(["Manufacturer", exam.manufacturer or "N/A"])
    rows.append(["Model", exam.model or "N/A"])
    for field_name, desc in exam.unit_conversions.items():
        rows.append([f"Units: {field_name}", desc])
    flow: list[Any] = []
    if multi:
        flow.append(Paragraph(f"Exam {exam.exam_id}", _H2))
    flow.append(_table(rows, [_CONTENT_WIDTH * 0.5, _CONTENT_WIDTH * 0.5]))
    flow.append(Spacer(1, 8))
    return flow


def _corrections_flow(payload: ExportPayload) -> list:
    flow: list[Any] = [Paragraph("Correction factors", _H2)]
    widths = [_CONTENT_WIDTH * 0.36] + [_CONTENT_WIDTH * 0.16] * 4
    if payload.is_multi_exam:
        for exam in payload.exams:
            flow.append(Paragraph(f"Exam {exam.exam_id}", _BODY))
            flow.append(_table([CORRECTION_HEADER] + [correction_row(s) for s in exam.corrections], widths))
            flow.append(Spacer(1, 4))
        flow.append(Paragraph("Cumulative (kerma-weighted)", _BODY))
    flow.append(_table([CORRECTION_HEADER] + [correction_row(s) for s in payload.cumulative.corrections], widths))
    if corrections_use_kerma_meter(payload):
        flow.append(Paragraph(KERMA_METER_WEIGHTING_FOOTNOTE, _BODY))
    return flow


def _images_flow(payload: ExportPayload) -> list:
    flow: list[Any] = [Paragraph("Dose-map images", _H2)]
    for entry in payload.images:
        flow.append(Paragraph(entry.label, _BODY))
        if entry.png_bytes is not None:
            img = Image(io.BytesIO(entry.png_bytes))
            ratio = min(_CONTENT_WIDTH / img.drawWidth, 1.0)
            img.drawWidth *= ratio
            img.drawHeight *= ratio
            flow.append(img)
        else:
            flow.append(_p(entry.error_message or "Image unavailable (kaleido/export error)", _BODY))
        flow.append(Spacer(1, 8))
    return flow


def _story(payload: ExportPayload) -> list:
    story: list[Any] = [
        Paragraph(payload.meta.report_title, _H1),
        _p(
            f"{payload.meta.app_name} v{payload.meta.package_version} · "
            f"{payload.meta.execution_context} · {payload.meta.generated_at.isoformat(timespec='seconds')}",
            _BODY,
        ),
        Spacer(1, 8),
    ]
    story += _alert_box(payload)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Cumulative summary", _H2))
    story.append(_dosimetric_table(payload))
    story.append(PageBreak())

    story.append(Paragraph("Settings & equipment", _H2))
    for exam in payload.exams:
        story += _settings_flow(exam, payload.is_multi_exam)
    story.append(PageBreak())

    story += _corrections_flow(payload)
    if payload.images:
        story.append(PageBreak())
        story += _images_flow(payload)
    return story


def _build(payload: ExportPayload, target) -> None:
    doc = BaseDocTemplate(
        target, pagesize=_PAGE,
        leftMargin=_MARGIN, rightMargin=_MARGIN, topMargin=_MARGIN, bottomMargin=_MARGIN,
        title=payload.meta.report_title,
    )
    frame = Frame(_MARGIN, _MARGIN, _CONTENT_WIDTH, _PAGE[1] - 2 * _MARGIN, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    doc.build(_story(payload), canvasmaker=NumberedCanvas)


def render_pdf_bytes(payload: ExportPayload) -> bytes:
    buf = io.BytesIO()
    _build(payload, buf)
    return buf.getvalue()


def write_pdf(payload: ExportPayload, path: Path) -> None:
    atomic_write_private(path, render_pdf_bytes(payload))
