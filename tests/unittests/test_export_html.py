"""Phase 5 tests for the HTML report writer + format dispatcher."""

from __future__ import annotations

import base64

import pandas as pd

from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.export import ExportExamSource, ExportSource, collect_export_payload
from guiskindose.export.models import ImageEntry
from guiskindose.export.writers import FORMATS, render_bytes
from guiskindose.export.writers.html import render_html_bytes

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _payload():
    out = {
        "psd": 1.0, "air_kerma": 3.0,
        "patient": {"patient_type": "human", "patient": {
            "human_phantom": "hudfrid",
            "patient_skin_cells": {"x": [0.0, 1.0, 2.0], "y": [0.0, 0.0, 0.0], "z": [0.0, 0.0, 0.0]},
            "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]}}, "orientation": "hfs", "offsets": {}},
        "dose_map": [[1, 1.0]],
        "corrections": {"correction_value_index": [[0, 1]], "backscatter": [[1.2, 1.4]],
                        "inverse_square_law": [[0.9, 0.8]], "medium": [1.02], "table": [0.8], "kerma": [3.0]},
    }
    s = PyskindoseSettings(settings=load_settings_example_json(), output_format="dict")
    src = ExportSource(execution_context="cli", output_dict=out,
                       exams=[ExportExamSource("e1", pd.DataFrame(), None, "e1.dcm", s, (0, 0, 0))],
                       file_name="e1.dcm")
    return collect_export_payload(src, with_images=False)


def test_write_html_smoke():
    payload = _payload()
    payload.images = [ImageEntry(label="Dorsal", view="dorsal", exam_id=None, png_bytes=_PNG)]
    html = render_html_bytes(payload).decode()
    assert "<html" in html
    assert "data:image/png;base64," in html  # embedded image
    assert "schema_version" in html


def test_write_html_missing_image_notice():
    payload = _payload()
    payload.images = [ImageEntry(label="Dorsal", view="dorsal", exam_id=None, png_bytes=None,
                                 error_message="Image unavailable (kaleido/export error)")]
    html = render_html_bytes(payload).decode()
    assert "Image unavailable" in html


def test_dispatcher_all_formats():
    import pytest

    payload = _payload()
    for fmt in FORMATS:
        if fmt == "pdf":
            pytest.importorskip("reportlab")  # optional `export` extra
        data = render_bytes(payload, fmt)
        assert isinstance(data, bytes) and len(data) > 100
