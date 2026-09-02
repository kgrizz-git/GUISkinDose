"""Phase 3 tests for the PDF report writer."""

from __future__ import annotations

import pandas as pd
import pytest

from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.export import ExportExamSource, ExportSource, collect_export_payload
from guiskindose.export.models import ImageEntry

pytest.importorskip("reportlab")

from guiskindose.export.writers.pdf import render_pdf_bytes


def _settings():
    return PyskindoseSettings(settings=load_settings_example_json(), output_format="dict")


def _out():
    return {
        "psd": 1.0,
        "air_kerma": 3.0,
        "patient": {
            "patient_type": "human",
            "patient": {
                "human_phantom": "hudfrid",
                "patient_skin_cells": {"x": [0.0, 1.0, 2.0], "y": [0.0, 0.0, 0.0], "z": [0.0, 0.0, 0.0]},
                "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
            },
            "orientation": "hfs", "offsets": {},
        },
        "dose_map": [[0, 0.5], [1, 1.0], [2, 0.3]],
        "corrections": {
            "correction_value_index": [[0, 1], [2]],
            "backscatter": [[1.2, 1.4], [1.5]],
            "inverse_square_law": [[0.9, 0.8], [1.0]],
            "medium": [1.02, 1.03], "table": [0.8, 0.8], "kerma": [2.0, 1.0],
        },
    }


def _payload(*, source_file="exam1.dcm", with_images=False):
    src = ExportSource(
        execution_context="cli", output_dict=_out(),
        exams=[ExportExamSource("exam1", pd.DataFrame(), None, source_file, _settings(), (0, 0, 0))],
        file_name=source_file,
        calc_warnings=["HVL lookup snapped to grid edge for event 3"],
    )
    return collect_export_payload(src, with_images=with_images)


def test_write_pdf_smoke():
    data = render_pdf_bytes(_payload())
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_write_pdf_long_filename_wraps():
    long_name = "a_very_long_source_filename_" + "x" * 130 + ".dcm"
    data = render_pdf_bytes(_payload(source_file=long_name))  # must not raise
    assert data.startswith(b"%PDF")


def test_write_pdf_no_images():
    payload = _payload()
    payload.images = [
        ImageEntry(label="Dorsal", view="dorsal", exam_id=None, png_bytes=None,
                   error_message="Image unavailable (kaleido/export error)")
    ]
    data = render_pdf_bytes(payload)
    assert data.startswith(b"%PDF")
