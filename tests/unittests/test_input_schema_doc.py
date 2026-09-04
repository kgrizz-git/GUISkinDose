"""Keep dev-docs/INPUT_SCHEMA_DETECTION.md consistent with the code.

This test is the enforcement mechanism for the schema-detection doc: if the
default mode, the ambiguity margin, the set of detectable schemas, or the marker
columns cited in the doc's fingerprint table drift from the code, this test
fails until the doc (and the marker lists below) are updated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guiskindose.input_adapters.column_mapper import _normalize_str
from guiskindose.input_adapters.registry import _AUTO_MIN_MARGIN, _SCHEMA_KNOWN_NAMES

DOC = Path(__file__).parent.parent.parent / "dev-docs" / "INPUT_SCHEMA_DETECTION.md"
REPO_ROOT = Path(__file__).parent.parent.parent

# Marker columns the doc's fingerprint table cites for each schema. Each must be
# (a) present in that schema's code fingerprint and (b) mentioned in the doc.
MARKERS: dict[str, list[str]] = {
    "normalized": ["model", "K_IRP", "kVp", "DSD", "DSI"],
    "generic_rdsr_like": ["ManufacturerModelName", "KVP_kV", "DoseRP_Gy"],
    "radimetrics": ["Device", "kVp kV", "DAP (Total) Gy-cm2"],
    "dosetrack": ["Equipment Name", "Tube Voltage Peak (kV)", "Plane Code"],
}


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert DOC.exists(), f"Missing schema-detection doc: {DOC}"
    return DOC.read_text(encoding="utf-8")


def test_cli_default_is_auto():
    """The CLI's --input-schema argparse default must be 'auto'."""
    from guiskindose.main import get_argument_parser

    ns = get_argument_parser([])
    assert ns.input_schema == "auto", (
        f"CLI --input-schema default is {ns.input_schema!r}, expected 'auto'"
    )


def test_gui_default_is_auto():
    from guiskindose.gui.state import AppState

    assert AppState().input_schema == "auto"


def test_all_scored_schemas_are_documented(doc_text: str):
    for name, _known in _SCHEMA_KNOWN_NAMES:
        assert f"`{name}`" in doc_text, f"Schema {name!r} is scored in code but not documented"


def test_margin_matches_code(doc_text: str):
    # The doc states the margin as a bold number, e.g. "**0.20**".
    assert f"**{_AUTO_MIN_MARGIN:.2f}**" in doc_text, (
        f"Doc does not state the current _AUTO_MIN_MARGIN ({_AUTO_MIN_MARGIN})"
    )


def test_marker_columns_exist_in_fingerprints():
    known_by_name = dict(_SCHEMA_KNOWN_NAMES)
    for schema, markers in MARKERS.items():
        norm_fingerprint = {_normalize_str(c) for c in known_by_name[schema]}
        for marker in markers:
            assert _normalize_str(marker) in norm_fingerprint, (
                f"Marker {marker!r} cited for {schema!r} is not in its code fingerprint"
            )


def test_marker_columns_appear_in_doc(doc_text: str):
    for markers in MARKERS.values():
        for marker in markers:
            assert marker in doc_text, f"Marker {marker!r} is not mentioned in the doc"


def test_registered_workflow_help_mentions_relevant_setting_tokens():
    import json

    registry = json.loads((REPO_ROOT / "dev-docs" / "help_registry.json").read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in registry["entries"]}
    expected_tokens = {
        "settings_positioning": ["scale_lat", "scale_ap", "scale_lon", "table_origin"],
        "settings_below_floor_kvp": ["below_floor_kvp_policy", "manual_below_floor_kvp"],
        "geometry": ["table_origin"],
        "calculate": ["below_floor_kvp_policy", "manual_below_floor_kvp", "table_origin"],
    }
    help_root = REPO_ROOT / registry["source_dir"]
    for help_id, tokens in expected_tokens.items():
        text = (help_root / entries[help_id]["source"]).read_text(encoding="utf-8")
        for token in tokens:
            assert token in text, f"{entries[help_id]['source']} does not mention {token}"
