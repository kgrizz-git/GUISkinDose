"""Phase 6 tests for the DOCX report writer."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.export import ExportExamSource, ExportSource, collect_export_payload
from guiskindose.export.models import ImageEntry

pytest.importorskip("docx")

from guiskindose.export.writers.docx import render_docx_bytes


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


def test_write_docx_smoke():
    from docx import Document  # type: ignore[import-untyped]

    data = render_docx_bytes(_payload())
    assert data[:2] == b"PK"  # docx is a zip
    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "MyPySkinDose" in text


def test_write_docx_missing_image_notice():
    payload = _payload()
    payload.images = [ImageEntry(label="Dorsal", view="dorsal", exam_id=None, png_bytes=None,
                                 error_message="Image unavailable (kaleido/export error)")]
    data = render_docx_bytes(payload)  # must not raise
    assert data[:2] == b"PK"
