"""Tests for the value-suppressed DICOM scanner adapter."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from scripts import run_dicom_phi_advisory as dicom_advisory
from scripts.run_dicom_phi_advisory import finding_count


def test_finding_count_uses_only_structured_lists() -> None:
    payload = {
        "tag_findings": [{"value": "suppressed"}],
        "ocr_findings": [{"text": "suppressed"}, {"text": "suppressed"}],
        "status": "review",
    }

    assert finding_count(payload) == 3
    assert finding_count([payload]) == 0


def test_nonzero_scanner_status_without_payload_is_still_an_unreviewed_finding(tmp_path, monkeypatch) -> None:
    """A scanner's finding exit status must not be converted into a clean receipt."""
    root = tmp_path / "snapshot"
    root.mkdir()
    source = root / "fixture.dcm"
    source.write_bytes(b"synthetic")
    temporary = tmp_path / "reports"
    temporary.mkdir()

    def fake_run(argv, **_kwargs):
        output = Path(next(arg for arg in argv if str(arg).endswith(".json")))
        output.write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(dicom_advisory.subprocess, "run", fake_run)
    monkeypatch.setattr(dicom_advisory, "is_hash_pinned_approved", lambda *_args, **_kwargs: False)

    assert dicom_advisory._scan_dicom_path("dicom-phi-scan", root, temporary, 0, source.relative_to(root)) == (1, 0)
