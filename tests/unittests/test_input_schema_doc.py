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
from guiskindose.input_adapters.registry import (
    _AUTO_MIN_HITS,
    _AUTO_MIN_MARGIN,
    _SCHEMA_KNOWN_NAMES,
    _TRIGGER_EXCLUSIONS,
)

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
    assert ns.input_schema == "auto", f"CLI --input-schema default is {ns.input_schema!r}, expected 'auto'"


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


def test_hit_floor_matches_code(doc_text: str):
    """The doc states the minimum known-column count auto-detect requires."""
    phrase = f"at least **{_AUTO_MIN_HITS}** known columns"
    assert phrase in doc_text.lower(), f"Doc does not state the hit floor {phrase!r}"


def test_documented_radimetrics_recall_matches_shipped_examples(doc_text: str):
    """The maintainer page's Radimetrics hit counts are the shipped examples, not a full match."""
    from guiskindose import get_path_to_example_tabular_files
    from guiskindose.input_adapters.radimetrics import RADIMETRICS_COLUMN_NAMES
    from guiskindose.input_adapters.registry import _schema_views
    from guiskindose.input_adapters.tabular_loader import load

    lowered = doc_text.lower()
    assert "perfect recall" not in lowered
    assert f"fingerprint has {len(RADIMETRICS_COLUMN_NAMES)} names" in lowered
    examples = get_path_to_example_tabular_files()
    expected = {
        "radimetrics_example_newer_export_single_tube.csv": "newer example matches",
        "radimetrics_example_older_export_biplane.csv": "older example matches",
    }
    for filename, label in expected.items():
        views = _schema_views(load(examples / filename).raw_df)
        hits = next(hit_count for name, _score, _eligible, hit_count, _triggered in views if name == "radimetrics")
        assert f"{label} {hits} of them" in lowered, f"{filename} hit count {hits} is not in the doc"


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


def test_generic_rdsr_trigger_exclusions_in_score_only_cell(doc_text: str):
    """Every generic_rdsr_like trigger exclusion is named in that row's score-only column."""
    marker = "### Distinctive markers"
    start = doc_text.find(marker)
    assert start != -1, f"Doc is missing {marker!r}"
    section = doc_text[start:]
    score_only = ""
    for line in section.splitlines():
        if line.startswith("| `generic_rdsr_like`"):
            cells = [part.strip() for part in line.split("|")]
            assert len(cells) >= 4, "Distinctive-markers table row for generic_rdsr_like is malformed"
            score_only = cells[3].lower()
            break
    assert score_only, "Distinctive-markers table has no generic_rdsr_like row"
    for name in _TRIGGER_EXCLUSIONS["generic_rdsr_like"]:
        assert name in score_only, (
            f"Score-only cell for generic_rdsr_like omits exclusion {name!r}; update INPUT_SCHEMA_DETECTION.md"
        )


def test_distinctive_markers_are_documented(doc_text: str):
    """The eligibility rule and its Radimetrics/DoseTrack markers stay in the doc."""
    from guiskindose.input_adapters.registry import _RADIMETRICS_TRIGGER_SUBSTRINGS, _SCHEMA_TRIGGERS

    lowered = doc_text.lower()
    assert "distinctive marker" in lowered
    assert "do not elect a schema by themselves" in lowered
    assert "example columns the fingerprint recognizes" in lowered
    for token in _RADIMETRICS_TRIGGER_SUBSTRINGS:
        assert token in lowered, f"Radimetrics trigger {token!r} is not documented"
    for trigger in _SCHEMA_TRIGGERS["dosetrack"]:
        assert trigger in lowered, f"DoseTrack trigger {trigger!r} is not documented"
    for spelling in ("stationname", "deviceserialnumber", "acquisition_type_code"):
        assert spelling in lowered, f"Elector spelling {spelling!r} is not documented"


def test_user_and_maintainer_docs_agree_with_code():
    """The in-app/user page and the maintainer page both state the code's facts.

    Facts are taken from the detection constants, the DoseTrack manufacturer map,
    and the unimplemented vendor stubs, so a renamed marker or a new stub fails
    here until both pages are updated.
    """
    from guiskindose.input_adapters.dosetrack import MODEL2MANUF
    from guiskindose.input_adapters.registry import (
        _AUTO_MIN_HITS,
        _RADIMETRICS_TRIGGER_SUBSTRINGS,
        _SCHEMA_TRIGGERS,
    )
    from guiskindose.input_adapters.stubs import STUB_VENDORS

    user_text = (REPO_ROOT / "docs/source/gui_help/input_formats.md").read_text(encoding="utf-8").lower()
    maintainer = DOC.read_text(encoding="utf-8").lower()
    facts = list(_RADIMETRICS_TRIGGER_SUBSTRINGS)
    facts.extend(_SCHEMA_TRIGGERS["dosetrack"])
    for model, manufacturer in MODEL2MANUF.items():
        facts.append(model.lower())
        facts.append(manufacturer.lower())
    facts.extend(label.lower() for label in STUB_VENDORS.values())
    facts.extend((".dcm", "not yet implemented", "forward-filled", "fluoroscopy", "al;cu", "µa"))
    facts.append(f"at least **{_AUTO_MIN_HITS}** known columns")
    facts.extend(("stationname", "deviceserialnumber", "acquisition_type_code", "reference-point dose"))
    for fact in facts:
        assert fact in user_text, f"User input-format page omits {fact!r}"
        assert fact in maintainer, f"INPUT_SCHEMA_DETECTION.md omits {fact!r}"


def test_registered_workflow_help_mentions_relevant_setting_tokens():
    """Registered workflow help pages mention reproducible setting key names.

    Guards against help prose drifting from ``PyskindoseSettings`` / GUI state
    field names (for example ``below_floor_kvp_manual`` vs obsolete aliases).
    """
    import json

    registry = json.loads((REPO_ROOT / "dev-docs" / "help_registry.json").read_text(encoding="utf-8"))
    entries = {entry["id"]: entry for entry in registry["entries"]}
    expected_tokens = {
        "settings_positioning": ["scale_lat", "scale_ap", "scale_lon", "table_origin"],
        "settings_below_floor_kvp": ["below_floor_kvp_policy", "below_floor_kvp_manual"],
        "geometry": ["table_origin"],
        "calculate": ["below_floor_kvp_policy", "below_floor_kvp_manual", "table_origin"],
    }
    help_root = REPO_ROOT / registry["source_dir"]
    for help_id, tokens in expected_tokens.items():
        text = (help_root / entries[help_id]["source"]).read_text(encoding="utf-8")
        for token in tokens:
            assert token in text, f"{entries[help_id]['source']} does not mention {token}"
