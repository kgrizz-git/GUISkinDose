"""Tests for the export path (refactor plan Phase 1.2).

Two concerns:

1. ``format_export_data`` — the core JSON/dict export structure produced by a
   real end-to-end calculation. Pins the top-level keys, JSON-serializability,
   and absence of NaN (the assessment flagged ad-hoc NaN handling).
2. The GUI tabular-provenance embedding helpers (``_tabular_input_meta`` and
   ``_inject_html_tabular_meta``) extracted from the export closures so they are
   unit-testable and no longer duplicated between JSON and HTML export paths.
"""

from __future__ import annotations

import json
import logging
import math
from types import SimpleNamespace

import pydicom
import pytest

from mypyskindose import get_path_to_example_rdsr_files, load_settings_example_json
from mypyskindose.analyze_data import analyze_data
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_EXPECTED_TOP_KEYS = {
    "psd", "air_kerma", "patient", "table", "pad", "dose_map", "corrections", "events"
}


@pytest.fixture(autouse=True)
def _quiet_logs():
    """The calculation logs verbosely at DEBUG; keep test output readable."""
    logging.getLogger("mypyskindose").setLevel(logging.WARNING)
    yield


def _settings(output_format: str) -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "cylinder"  # fastest phantom for a quick test
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    return PyskindoseSettings(settings=base, output_format=output_format)


def _run(output_format: str):
    settings = _settings(output_format)
    parsed = rdsr_parser(pydicom.dcmread(str(_RDSR)), silence_pydicom_warnings=True)
    norm = rdsr_normalizer(parsed, settings=settings)
    return analyze_data(normalized_data=norm.copy(), settings=settings)


def _has_nan(obj) -> bool:
    if isinstance(obj, float):
        return math.isnan(obj)
    if isinstance(obj, dict):
        return any(_has_nan(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_nan(v) for v in obj)
    return False


# ── format_export_data: dict / json export ────────────────────────────────


def test_dict_export_has_expected_structure():
    out = _run("dict")
    assert isinstance(out, dict)
    assert set(out.keys()) == _EXPECTED_TOP_KEYS
    assert isinstance(out["psd"], float) and out["psd"] > 0
    assert isinstance(out["air_kerma"], float) and out["air_kerma"] > 0


def test_dict_export_is_json_serializable_without_nan():
    out = _run("dict")
    assert not _has_nan(out), "export contains NaN — not valid JSON"
    json.dumps(out)  # must not raise


def test_json_export_parses_back_to_same_keys():
    out_json = _run("json")
    assert isinstance(out_json, str)
    parsed = json.loads(out_json)
    assert set(parsed.keys()) == _EXPECTED_TOP_KEYS
    assert parsed["psd"] > 0


def test_dose_map_is_sparse_positive_entries():
    """to_dict() makes the dose map sparse: only (index, dose>0) pairs."""
    out = _run("dict")
    assert isinstance(out, dict)
    dose_map = out["dose_map"]
    assert isinstance(dose_map, list)
    assert all(dose > 0.0 for _, dose in dose_map)


# ── GUI provenance embedding helpers ──────────────────────────────────────

pytest.importorskip("nicegui")
# The provenance helpers were relocated from app.py to io_helpers.py (refactor
# plan Phase 3.3b); io_helpers has no nicegui dependency of its own.
import mypyskindose.gui.io_helpers as gui_io  # noqa: E402


def _fake_provenance():
    return SimpleNamespace(
        schema_name="radimetrics",
        detected_encoding="utf-8",
        detected_delimiter=",",
        header_row_index=3,
        column_map={"DAP (Total) Gy-cm2": "DoseAreaProduct_Gym2"},
    )


def test_tabular_input_meta_shape_and_serializable():
    meta = gui_io._tabular_input_meta(
        "export.csv", _fake_provenance(), swap_lat_lon=True, warnings=["w1", "w2"]
    )
    assert meta["source_file"] == "export.csv"
    assert meta["schema"] == "radimetrics"
    assert meta["header_row_index"] == 3
    assert meta["lat_lon_swapped"] is True
    assert meta["warnings"] == ["w1", "w2"]
    json.dumps(meta)  # embedded in JSON export — must serialize


def test_inject_html_meta_inserts_comment_after_head():
    html = b"<html><head><title>x</title></head><body>map</body></html>"
    meta = {"schema": "dosetrack", "warnings": []}
    out = gui_io._inject_html_tabular_meta(html, meta)
    assert b"dosetrack" in out
    assert b"<body>map</body>" in out  # original content preserved
    # comment appears exactly once
    assert out.count(b"mypyskindose:tabular_input") == 1
    # and is positioned immediately after the OPENING <head>, before <title>
    # (guards against anchoring on </head> or elsewhere).
    comment_pos = out.index(b"mypyskindose:tabular_input")
    title_pos = out.index(b"<title>")
    head_close_pos = out.index(b"</head>")
    assert comment_pos < title_pos, "comment must precede <title> (right after opening <head>)"
    assert comment_pos < head_close_pos, "comment must be inside the head, before </head>"


def test_inject_html_meta_noop_without_head():
    html = b"<html><body>no head here</body></html>"
    out = gui_io._inject_html_tabular_meta(html, {"schema": "x"})
    assert out == html  # unchanged when there is no <head>


def test_inject_html_meta_only_first_head_annotated():
    html = b"<head>A</head><head>B</head>"
    out = gui_io._inject_html_tabular_meta(html, {"schema": "x"})
    assert out.count(b"mypyskindose:tabular_input") == 1
