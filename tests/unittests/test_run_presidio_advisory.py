"""Tests for the local Presidio advisory runner without requiring its optional dependency."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

from scripts.run_presidio_advisory import MAX_TEXT_BYTES, PII_ENTITIES, Finding, read_text, scan_paths, tracked_paths


class FakeEngine:
    def analyze(
        self,
        *,
        text: str,
        language: str,
        entities: list[str],
        score_threshold: float,
    ) -> list[SimpleNamespace]:
        assert language == "en"
        assert entities == PII_ENTITIES
        assert math.isclose(score_threshold, 0.85, rel_tol=0.0, abs_tol=1e-9)
        return [SimpleNamespace(start=text.index("token"), entity_type="EMAIL_ADDRESS", score=0.91)]


def test_scan_paths_reports_safe_location_metadata(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("first line\ncontains token\n", encoding="utf-8")

    findings = scan_paths(FakeEngine(), tmp_path, [source])

    assert findings == [Finding(path=Path("note.txt"), line=2, entity_type="EMAIL_ADDRESS", score=0.91)]


def test_scan_paths_skips_binary_content(tmp_path: Path) -> None:
    source = tmp_path / "image"
    source.write_bytes(b"not text\x00")

    assert scan_paths(FakeEngine(), tmp_path, [source]) == []


def test_scan_paths_person_detection_requires_opt_in(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("contains token\n", encoding="utf-8")

    class PersonEngine(FakeEngine):
        def analyze(self, **kwargs):
            assert kwargs["entities"] == [*PII_ENTITIES, "PERSON"]
            return [SimpleNamespace(start=0, entity_type="PERSON", score=0.85)]

    findings = scan_paths(PersonEngine(), tmp_path, [source], include_person=True)

    assert findings == [Finding(path=Path("note.txt"), line=1, entity_type="PERSON", score=0.85)]


def test_read_text_skips_oversized_content(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_bytes(b"a" * (MAX_TEXT_BYTES + 1))

    assert read_text(source) is None


def test_materialized_snapshot_discovery_does_not_require_git(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    included = tmp_path / "docs" / "note.md"
    included.write_text("synthetic text", encoding="utf-8")
    (tmp_path / "opaque.bin").write_bytes(b"binary\x00")

    assert tracked_paths(tmp_path, require_git=False) == [included]
