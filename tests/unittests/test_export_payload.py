"""Phase 1 tests for the Rich Report Export payload collector.

Covers plan items 1.8.1–1.8.10: single/multi-exam collection, provenance
branches, PSD peak, sparse-hit corrections, kaleido-failure resilience, and the
all-miss scenario. Uses lightweight synthetic outputs plus one real fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from mypyskindose import PyskindoseSettings, load_settings_example_json
from mypyskindose.export import (
    ExportError,
    ExportExamSource,
    ExportSource,
    collect_export_payload,
)
from mypyskindose.input_adapters.models import InputProvenance

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "export" / "single_exam_siemens.json"


# ── builders ──────────────────────────────────────────────────────────────────


def _settings() -> PyskindoseSettings:
    return PyskindoseSettings(settings=load_settings_example_json(), output_format="dict")


def _patient(n_cells: int = 3) -> dict:
    return {
        "human_phantom": "hudfrid",
        "patient_skin_cells": {
            "x": [float(i) for i in range(n_cells)],
            "y": [0.0] * n_cells,
            "z": [0.0] * n_cells,
        },
        "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
    }


def _output_dict(*, dose_sparse, hits, k_bs, k_isq, k_med, k_tab, kerma, n_cells=3):
    dense = np.zeros(n_cells)
    for idx, dose in dose_sparse:
        dense[idx] = dose
    return {
        "psd": float(dense.max()) if dense.size else 0.0,
        "air_kerma": float(sum(kerma)),
        "patient": {"patient_type": "human", "patient": _patient(n_cells), "orientation": "hfs", "offsets": {}},
        "dose_map": dose_sparse,
        "corrections": {
            "correction_value_index": hits,
            "backscatter": k_bs,
            "inverse_square_law": k_isq,
            "medium": k_med,
            "table": k_tab,
            "kerma": kerma,
        },
    }


def _two_event_output():
    """2 events: e0 hits cells [0,1] (kerma 2.0), e1 hits [2] (kerma 1.0)."""
    return _output_dict(
        dose_sparse=[(0, 0.5), (1, 1.0), (2, 0.3)],
        hits=[[0, 1], [2]],
        k_bs=[[1.2, 1.4], [1.5]],
        k_isq=[[0.9, 0.8], [1.0]],
        k_med=[1.02, 1.03],
        k_tab=[0.8, 0.8],
        kerma=[2.0, 1.0],
    )


def _single_source(output_dict, *, provenance=None, df=None):
    return ExportSource(
        execution_context="cli",
        output_dict=output_dict,
        exams=[
            ExportExamSource(
                exam_id="exam1",
                normalized_data=(df if df is not None else pd.DataFrame()),
                provenance=provenance,
                source_file="exam1.dcm",
                effective_settings=_settings(),
                patient_offset=(0.0, 0.0, 0.0),
            )
        ],
        file_name="exam1.dcm",
    )


def _fake_output_obj(output_dict):
    """A minimal stand-in for a PySkinDoseOutput object (multi-exam path)."""
    corr = output_dict["corrections"]
    dense = np.zeros(len(output_dict["patient"]["patient"]["patient_skin_cells"]["x"]))
    for idx, dose in output_dict["dose_map"]:
        dense[idx] = dose
    return SimpleNamespace(
        PSD=output_dict["psd"],
        AirKerma=output_dict["air_kerma"],
        Patient={"patient": SimpleNamespace(to_dict=lambda p=output_dict["patient"]["patient"]: p)},
        DoseMap=dense,
        Hits=corr["correction_value_index"],
        BackscatterCorrection=corr["backscatter"],
        InverseSquareLawCorrection=corr["inverse_square_law"],
        MediumCorrection=corr["medium"],
        TableCorrection=corr["table"],
        Events=SimpleNamespace(kerma=corr["kerma"]),
    )


# ── 1.8.1 single-exam dict ─────────────────────────────────────────────────────


def test_payload_single_exam_dict():
    payload = collect_export_payload(_single_source(_two_event_output()), with_images=False)
    assert payload.is_multi_exam is False
    m = payload.cumulative.metrics
    assert m.psd == pytest.approx(1.0)
    assert m.air_kerma == pytest.approx(3.0)
    assert m.peak_vertex_index == 1  # cell 1 has dose 1.0
    # DICOM branch (no provenance)
    assert payload.provenance.source_type == "dicom"
    assert payload.provenance.schema_name == "rdsr"
    # k_med dose-weighted mean = (2*1.02 + 1*1.03)/3
    kmed = next(c for c in payload.exams[0].corrections if c.key == "k_med")
    assert kmed.dose_weighted_mean == pytest.approx((2 * 1.02 + 1.03) / 3)


# ── 1.8.2 multi-exam object ────────────────────────────────────────────────────


def test_payload_multi_exam_object():
    o1 = _two_event_output()
    o2 = _two_event_output()
    agg = np.array([1.0, 2.0, 0.6])  # element-wise sum of the two identical maps
    result = SimpleNamespace(
        exams=[
            SimpleNamespace(exam_id="A", source_file="a.dcm", patient_offset=[0, 0, 0],
                            output=_fake_output_obj(o1), warnings=[]),
            SimpleNamespace(exam_id="B", source_file="b.dcm", patient_offset=[0, 0, 0],
                            output=_fake_output_obj(o2), warnings=[]),
        ],
        aggregate_dose_map=agg,
        aggregate_psd=2.0,
        total_events=4,
        warnings=["run warning"],
    )
    src = ExportSource(
        execution_context="cli",
        multi_exam_result=result,
        exams=[
            ExportExamSource("A", pd.DataFrame(), None, "a.dcm", _settings(), (0, 0, 0)),
            ExportExamSource("B", pd.DataFrame(), None, "b.dcm", _settings(), (0, 0, 0)),
        ],
    )
    payload = collect_export_payload(src, with_images=False)
    assert payload.is_multi_exam is True
    assert len(payload.exams) == 2
    # Cumulative air kerma = explicit sum (3 + 3)
    assert payload.cumulative.metrics.air_kerma == pytest.approx(6.0)
    assert payload.cumulative.metrics.psd == pytest.approx(2.0)
    assert payload.cumulative.metrics.peak_vertex_index == 1
    # Primary contributing exam present and sums to full contribution
    pce = payload.cumulative.primary_contributing_exam
    assert pce is not None
    assert pce.exam_id in {"A", "B"}
    assert pce.dose_fraction == pytest.approx(0.5)
    assert "run warning" in payload.warnings.run_warnings


# ── 1.8.3 / 1.8.4 provenance branches ──────────────────────────────────────────


def test_payload_dicom_provenance_fallback():
    payload = collect_export_payload(_single_source(_two_event_output()), with_images=False)
    assert payload.provenance.source_type == "dicom"
    assert payload.provenance.schema_name == "rdsr"
    assert payload.provenance.metadata_confidence == "dicom_tags"
    assert payload.provenance.column_map == {}


def test_payload_tabular_provenance():
    prov = InputProvenance(
        source_type="csv",
        schema_name="dosetrack",
        original_filename="export.csv",
        header_row_index=3,
        detected_encoding="utf-8",
        detected_delimiter=",",
        sheet_name=None,
        column_map={"kVp (kV)": "kVp"},
        unit_conversions={},
        warnings=["inferred manufacturer"],
    )
    payload = collect_export_payload(_single_source(_two_event_output(), provenance=prov), with_images=False)
    assert payload.provenance.source_type == "csv"
    assert payload.provenance.schema_name == "dosetrack"
    assert payload.provenance.encoding == "utf-8"
    assert payload.provenance.delimiter == ","
    assert payload.provenance.header_row_index == 3
    assert payload.provenance.column_map == {"kVp (kV)": "kVp"}
    assert payload.provenance.metadata_confidence == "tabular_inferred"
    assert "inferred manufacturer" in payload.provenance.warnings


# ── 1.8.5 PSD peak vertex ──────────────────────────────────────────────────────


def test_psd_peak_vertex_index():
    out = _output_dict(
        dose_sparse=[(0, 0.1), (2, 5.0)], hits=[[0, 2]],
        k_bs=[[1.0, 1.0]], k_isq=[[1.0, 1.0]], k_med=[1.0], k_tab=[1.0], kerma=[1.0], n_cells=3,
    )
    payload = collect_export_payload(_single_source(out), with_images=False)
    m = payload.cumulative.metrics
    assert m.peak_vertex_index == 2
    assert m.peak_xyz == (2.0, 0.0, 0.0)


# ── 1.8.6 sparse-hit corrections with a zero-hit pulse ─────────────────────────


def test_correction_sparse_hits():
    # 3 events: e0 hits [0,1] k2, e1 hits [2] k1, e2 hits [] k5 (zero-dose pulse)
    out = _output_dict(
        dose_sparse=[(0, 0.5), (1, 1.0), (2, 0.3)],
        hits=[[0, 1], [2], []],
        k_bs=[[1.2, 1.4], [1.5], []],
        k_isq=[[0.9, 0.8], [1.0], []],
        k_med=[1.02, 1.03, 9.9],
        k_tab=[0.8, 0.8, 9.9],
        kerma=[2.0, 1.0, 5.0],
    )
    payload = collect_export_payload(_single_source(out), with_images=False)
    kbs = next(c for c in payload.exams[0].corrections if c.key == "k_bs")
    # per-event means [1.3, 1.5]; zero-hit event excluded
    assert kbs.minimum == pytest.approx(1.3)
    assert kbs.maximum == pytest.approx(1.5)
    # dose-weighted excludes the k=5 zero-hit pulse: (2*1.3 + 1*1.5)/3
    assert kbs.dose_weighted_mean == pytest.approx((2 * 1.3 + 1.5) / 3)


# ── 1.8.7 export without kaleido ───────────────────────────────────────────────


def test_export_without_kaleido(monkeypatch):
    import plotly.graph_objects as go

    def _boom(self, *a, **k):
        raise RuntimeError("kaleido missing")

    monkeypatch.setattr(go.Figure, "to_image", _boom)
    payload = collect_export_payload(_single_source(_two_event_output()), with_images=True)
    assert payload.images  # entries exist
    assert all(img.png_bytes is None for img in payload.images)
    assert all(img.error_message for img in payload.images)


# ── 1.8.8 build_export_source_from_gui ─────────────────────────────────────────


def test_build_export_source_from_gui():
    from mypyskindose.gui.export_source import build_export_source_from_gui
    from mypyskindose.gui.state import AppState

    # single-exam branch
    st = AppState()
    st.output = _two_event_output()
    st.file_name = "case.dcm"
    src = build_export_source_from_gui(st)
    assert src.execution_context == "gui"
    assert src.output_dict is not None
    assert src.multi_exam_result is None
    assert src.exams[0].exam_id == "case.dcm"

    # multi-exam branch takes precedence
    st.multi_exam_result = SimpleNamespace(
        exams=[SimpleNamespace(exam_id="A", source_file="a.dcm", patient_offset=[0, 0, 0],
                               output=_fake_output_obj(_two_event_output()), warnings=[])],
        aggregate_dose_map=np.array([1.0, 1.0, 0.3]), aggregate_psd=1.0, total_events=2, warnings=[],
    )
    src2 = build_export_source_from_gui(st)
    assert src2.multi_exam_result is not None
    assert len(src2.exams) == 1


# ── 1.8.9 build_export_source_from_cli ─────────────────────────────────────────


def test_build_export_source_from_cli():
    from mypyskindose.export import build_export_source_from_cli

    src = build_export_source_from_cli(
        _settings(), output_dict=_two_event_output(), single_source_file="c.dcm", file_name="c.dcm"
    )
    assert src.execution_context == "cli"
    assert src.output_dict is not None
    assert src.exams[0].source_file == "c.dcm"
    payload = collect_export_payload(src, with_images=False)
    assert payload.cumulative.metrics.psd == pytest.approx(1.0)


# ── 1.8.10 all events miss the phantom ─────────────────────────────────────────


def test_all_exam_miss_scenario():
    out = _output_dict(
        dose_sparse=[], hits=[[], []], k_bs=[[], []], k_isq=[[], []],
        k_med=[1.0, 1.0], k_tab=[1.0, 1.0], kerma=[2.0, 1.0],
    )
    payload = collect_export_payload(_single_source(out), with_images=False)
    m = payload.cumulative.metrics
    assert m.psd == pytest.approx(0.0)
    assert m.peak_vertex_index is None
    assert m.peak_xyz is None
    for c in payload.exams[0].corrections:
        assert c.dose_weighted_mean is None
        assert c.mean is None


# ── no-result guard ────────────────────────────────────────────────────────────


def test_no_result_raises():
    with pytest.raises(ExportError):
        collect_export_payload(ExportSource(execution_context="cli"), with_images=False)


# ── real-fixture integration ───────────────────────────────────────────────────


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture not generated")
def test_payload_real_fixture():
    out = json.loads(FIXTURE.read_text())
    payload = collect_export_payload(_single_source(out), with_images=False)
    assert payload.cumulative.metrics.psd == pytest.approx(out["psd"])
    assert payload.cumulative.metrics.air_kerma == pytest.approx(out["air_kerma"])
    assert payload.meta.package_version != ""
