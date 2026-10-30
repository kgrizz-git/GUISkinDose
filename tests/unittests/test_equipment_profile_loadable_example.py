"""The packaged loadable example must pass the current capability gate.

The filled ``equipment_profile_example`` files preview the full schema and are
rejected by the initial coordinate-only gate. ``equipment_profile_loadable_example``
is the copy-ready file users start from today, so it must keep assembling.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guiskindose.equipment_profiles import (
    ExamCoordinateIdentity,
    FileSource,
    active_set_hash,
    assemble_session,
    bundled_coordinate_set,
    parse_csv_bytes,
    parse_json_bytes,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "example_data" / "equipment_profiles"


@pytest.mark.parametrize("suffix", ["json", "csv"])
def test_loadable_example_assembles(suffix: str) -> None:
    session = assemble_session(files=[FileSource(str(EXAMPLES / f"equipment_profile_loadable_example.{suffix}"))])
    (source,) = session.provenance.sources
    assert source.profile_ids == ("demo-scope-3000",)


def test_loadable_example_json_and_csv_match() -> None:
    json_profiles = parse_json_bytes((EXAMPLES / "equipment_profile_loadable_example.json").read_bytes()).profiles
    csv_profiles = parse_csv_bytes((EXAMPLES / "equipment_profile_loadable_example.csv").read_bytes()).profiles
    assert active_set_hash(json_profiles) == active_set_hash(csv_profiles)


def test_loadable_example_applies_as_a_complete_exact_match() -> None:
    session = assemble_session(files=[FileSource(str(EXAMPLES / "equipment_profile_loadable_example.json"))])
    settings_path = EXAMPLES.parents[1] / "normalization_settings.json"
    bundled = bundled_coordinate_set(json.loads(settings_path.read_bytes())["normalization_settings"])
    match = session.resolve(ExamCoordinateIdentity(manufacturer="Acme Imaging", model="DemoScope 3000", event_count=3), bundled)
    assert match.record.profile_id == "demo-scope-3000"
    assert len(match.record.fields) == 15
