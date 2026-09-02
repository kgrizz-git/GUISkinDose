"""HTML report writer (§5.1). Single self-contained file, embedded CSS + images.

``render_html_bytes(payload)`` for downloads; ``write_html(payload, path)`` for
filesystem writes.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

from guiskindose.safe_output import atomic_write_private

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
from ..models import ExportPayload

_CSS = """
body{font-family:Inter,system-ui,Arial,sans-serif;margin:2rem;color:#0f172a;background:#fff;}
h1{font-size:1.6rem;margin:0 0 .25rem;} h2{font-size:1.15rem;margin:1.5rem 0 .5rem;}
.meta{color:#64748b;font-size:.85rem;margin-bottom:1rem;}
table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.85rem;}
th,td{border:1px solid #e2e8f0;padding:.35rem .5rem;text-align:left;vertical-align:top;word-break:break-word;}
th{background:#e9ecef;font-weight:600;}
.alert{border:1.5px solid #b08800;border-radius:4px;padding:.5rem .75rem;margin:.35rem 0;}
.alert.warning{background:#__WARN__;} .alert.error{background:#__ERR__;} .alert.ok{background:#d4edda;}
figure{margin:1rem 0;} img{max-width:100%;height:auto;border:1px solid #e2e8f0;}
details{margin:.5rem 0;} summary{cursor:pointer;font-weight:600;}
""".replace("__WARN__", COLOR_WARNING).replace("__ERR__", COLOR_ERROR)


def _esc(value) -> str:
    """HTML-escape a value for safe embedding."""
    return html.escape(str(value))


def _table(rows: list[list], *, header: bool = True) -> str:
    """Render a list of rows as an HTML table."""
    out = ["<table>"]
    for i, row in enumerate(rows):
        tag = "th" if header and i == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}>{_esc(c)}</{tag}>" for c in row) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _alerts(payload: ExportPayload) -> str:
    """Render the executive-alerts HTML section."""
    parts = ["<h2>Executive alerts</h2>"]
    for text, severity in collect_alert_lines(payload):
        parts.append(f'<div class="alert {severity}">{_esc(text)}</div>')
    return "".join(parts)


def _settings_rows(exam) -> list[list[str]]:
    """Build Setting/Value rows for one exam's settings block."""
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
    return rows


def _images(payload: ExportPayload) -> str:
    """Render embedded dose-map images as an HTML section."""
    if not payload.images:
        return ""
    parts = ["<h2>Dose-map images</h2>"]
    for entry in payload.images:
        parts.append(f"<figure><figcaption>{_esc(entry.label)}</figcaption>")
        if entry.png_bytes is not None:
            b64 = base64.b64encode(entry.png_bytes).decode()
            parts.append(f'<img alt="{_esc(entry.label)}" src="data:image/png;base64,{b64}">')
        else:
            parts.append(f"<p>{_esc(entry.error_message or 'Image unavailable')}</p>")
        parts.append("</figure>")
    return "".join(parts)


def render_html_bytes(payload: ExportPayload) -> bytes:
    """Render the HTML report to an in-memory bytes payload."""
    m = payload.meta
    body = [
        f"<h1>{_esc(m.report_title)}</h1>",
        (f'<div class="meta">{_esc(m.app_name)} v{_esc(m.package_version)} · '
        f'{_esc(m.execution_context)} · {_esc(m.generated_at.isoformat(timespec="seconds"))} · '
        f'schema {m.schema_version}</div>'),
        _alerts(payload),
        "<h2>Cumulative summary</h2>",
        _table([["Metric", "Value"], *dosimetric_rows(payload.cumulative.metrics)]),
    ]

    if payload.is_multi_exam:
        headers = ["Metric"] + [e.exam_id for e in payload.exams] + ["Cumulative"]
        names = [r[0] for r in dosimetric_rows(payload.cumulative.metrics)]
        cols = [{r[0]: r[1] for r in dosimetric_rows(e.metrics)} for e in payload.exams]
        cum = {r[0]: r[1] for r in dosimetric_rows(payload.cumulative.metrics)}
        summary = [headers] + [[n, *[c.get(n, "N/A") for c in cols], cum.get(n, "N/A")] for n in names]
        body.append("<h2>Per-exam results</h2>")
        body.append(_table(summary))

    body.append("<h2>Correction factors</h2>")
    if payload.is_multi_exam:
        for exam in payload.exams:
            body.append(f"<details><summary>Exam {_esc(exam.exam_id)}</summary>")
            body.append(_table([CORRECTION_HEADER] + [correction_row(s) for s in exam.corrections]))
            body.append("</details>")
        body.append("<p>Cumulative (kerma-weighted)</p>")
    body.append(_table([CORRECTION_HEADER] + [correction_row(s) for s in payload.cumulative.corrections]))
    if corrections_use_kerma_meter(payload):
        body.append(f"<p><em>{_esc(KERMA_METER_WEIGHTING_FOOTNOTE)}</em></p>")

    body.append("<h2>Settings &amp; equipment</h2>")
    for exam in payload.exams:
        body.append(f"<details><summary>Exam {_esc(exam.exam_id)}</summary>")
        body.append(_table(_settings_rows(exam)))
        body.append("</details>")

    body.append(_images(payload))

    doc = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='schema_version' content='{m.schema_version}'>"
        f"<meta name='guiskindose_version' content='{_esc(m.package_version)}'>"
        f"<title>{_esc(m.report_title)}</title><style>{_CSS}</style></head>"
        f"<body>{''.join(body)}</body></html>"
    )
    return doc.encode("utf-8")


def write_html(payload: ExportPayload, path: Path) -> None:
    """Atomically write the HTML report to *path*."""
    atomic_write_private(path, render_html_bytes(payload))
