"""Unit tests for scripts/check_sonar_properties.py."""

from pathlib import Path

from scripts.check_sonar_properties import CONFIGURATION_FILES, SHARED_KEYS, check_sonar_properties


def write_configurations(root: Path, differing_key: str | None = None, missing_key: str | None = None) -> None:
    """Write minimal matching Sonar configurations, with an optional deliberate defect."""
    for filename in CONFIGURATION_FILES:
        lines = ["# Test configuration"]
        for key in SHARED_KEYS:
            if filename == ".sonarcloud.properties" and key == missing_key:
                continue
            value = "shared-value"
            if filename == ".sonarcloud.properties" and key == differing_key:
                value = "different-value"
            lines.append(f"{key}={value}")
        (root / filename).write_text("\n".join(lines), encoding="utf-8")


def test_check_sonar_properties_accepts_matching_shared_settings(tmp_path: Path) -> None:
    write_configurations(tmp_path)

    assert check_sonar_properties(tmp_path) is True


def test_check_sonar_properties_rejects_different_shared_setting(tmp_path: Path) -> None:
    write_configurations(tmp_path, differing_key="sonar.exclusions")

    assert check_sonar_properties(tmp_path) is False


def test_check_sonar_properties_rejects_missing_shared_setting(tmp_path: Path) -> None:
    write_configurations(tmp_path, missing_key="sonar.test.exclusions")

    assert check_sonar_properties(tmp_path) is False
