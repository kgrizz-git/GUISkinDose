"""Unit tests for scripts/check_cloud_scanner_exclusions.py."""

from pathlib import Path

from scripts.check_cloud_scanner_exclusions import (
    CLOUD_SENSITIVE_EXCLUSIONS,
    CODERABBIT_CONFIGURATION_FILE,
    SONAR_CONFIGURATION_FILES,
    check_cloud_scanner_exclusions,
)


def write_configurations(root: Path) -> None:
    """Write minimal valid cloud-scanner configurations."""
    patterns = ",".join(sorted(CLOUD_SENSITIVE_EXCLUSIONS))
    for filename in SONAR_CONFIGURATION_FILES:
        (root / filename).write_text(f"sonar.exclusions={patterns}\n", encoding="utf-8")
    filters = "\n".join(f'    - "!{pattern}"' for pattern in sorted(CLOUD_SENSITIVE_EXCLUSIONS))
    (root / CODERABBIT_CONFIGURATION_FILE).write_text(
        f"reviews:\n  path_filters:\n{filters}\n", encoding="utf-8"
    )


def test_check_cloud_scanner_exclusions_accepts_required_patterns(tmp_path: Path) -> None:
    write_configurations(tmp_path)

    assert check_cloud_scanner_exclusions(tmp_path) is True


def test_check_cloud_scanner_exclusions_rejects_missing_sonar_dicom_pattern(tmp_path: Path) -> None:
    write_configurations(tmp_path)
    sonar_path = tmp_path / SONAR_CONFIGURATION_FILES[0]
    sonar_path.write_text("sonar.exclusions=**/*.dcm\n", encoding="utf-8")

    assert check_cloud_scanner_exclusions(tmp_path) is False


def test_check_cloud_scanner_exclusions_rejects_missing_coderabbit_dicom_pattern(tmp_path: Path) -> None:
    write_configurations(tmp_path)
    (tmp_path / CODERABBIT_CONFIGURATION_FILE).write_text(
        'reviews:\n  path_filters:\n    - "!**/*.dcm"\n', encoding="utf-8"
    )

    assert check_cloud_scanner_exclusions(tmp_path) is False


def test_check_cloud_scanner_exclusions_diagnostics_do_not_expose_configuration_details(
    tmp_path: Path, capsys
) -> None:
    write_configurations(tmp_path)
    (tmp_path / CODERABBIT_CONFIGURATION_FILE).write_text("reviews:\n", encoding="utf-8")

    assert check_cloud_scanner_exclusions(tmp_path) is False

    output = capsys.readouterr().out
    assert "*.dicom" not in output
    assert str(tmp_path) not in output
