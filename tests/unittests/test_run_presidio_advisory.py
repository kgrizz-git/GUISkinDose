"""Tests for the local Presidio advisory runner without requiring its optional dependency."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts.run_presidio_advisory import MAX_TEXT_BYTES, PII_ENTITIES, Finding, read_text, scan_paths


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
        assert score_threshold == 0.5
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


def test_read_text_skips_oversized_content(tmp_path: Path) -> None:
    source = tmp_path / "large.txt"
    source.write_bytes(b"a" * (MAX_TEXT_BYTES + 1))

    assert read_text(source) is None
