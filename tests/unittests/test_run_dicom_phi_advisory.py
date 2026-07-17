"""Tests for the value-suppressed DICOM scanner adapter."""

from scripts.run_dicom_phi_advisory import finding_count


def test_finding_count_uses_only_structured_lists() -> None:
    payload = {
        "tag_findings": [{"value": "suppressed"}],
        "ocr_findings": [{"text": "suppressed"}, {"text": "suppressed"}],
        "status": "review",
    }

    assert finding_count(payload) == 3
    assert finding_count([payload]) == 0
