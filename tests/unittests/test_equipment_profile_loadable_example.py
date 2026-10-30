"""The packaged loadable example must pass the current capability gate.

The filled ``equipment_profile_example`` files preview the full schema and are
rejected by the initial coordinate-only gate. ``equipment_profile_loadable_example``
is the copy-ready file users start from today, so it must keep assembling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guiskindose.equipment_profiles import (
    FileSource,
    active_set_hash,
    assemble_session,
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
