"""Tests for conditional privacy admission policy and receipt routing."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.privacy_admission import (
    ScannerRule,
    command_check,
    digest_mapping,
    forbidden_paths,
    missing_ignore_patterns,
    normalize_path,
    phi_filename_findings,
    receipt_path,
    required_rules,
    verify_receipt,
)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def initialize_policy_repository(root: Path) -> None:
    (root / "dev-docs").mkdir()
    (root / "dev-docs" / "privacy_admission_policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "receipt_max_age_hours": 168,
                "protected_ignore_patterns": ["tmp/"],
                "never_track_prefixes": ["tmp/"],
                "never_track_names": [],
                "never_track_patterns": [],
                "scanners": [],
            }
        ),
        encoding="utf-8",
    )
    (root / ".gitignore").write_text("tmp/\n", encoding="utf-8")
    git(root, "init")
    git(root, "add", ".gitignore", "dev-docs/privacy_admission_policy.json")
    git(root, "-c", "user.name=Privacy Test", "-c", "user.email=privacy-test", "commit", "-m", "baseline")


def test_normalize_path_preserves_dot_directory() -> None:
    assert normalize_path("./.scannerwork/report-task.txt") == ".scannerwork/report-task.txt"
    assert normalize_path(r"tmp\report.json") == "tmp/report.json"


def test_protected_ignore_patterns_must_remain_present() -> None:
    ignore_bytes = b"tmp/\n*.log\n"
    policy = {"protected_ignore_patterns": ["tmp/", "*.log", ".scannerwork/"]}

    assert missing_ignore_patterns(ignore_bytes, policy) == [".scannerwork/"]


def test_never_track_policy_blocks_force_added_roots_and_names() -> None:
    policy = {
        "never_track_prefixes": ["tmp/", ".scannerwork/"],
        "never_track_names": [".DS_Store"],
        "never_track_patterns": ["*.trace", "coverage.xml"],
    }

    assert forbidden_paths(
        policy,
        [
            "src/app.py",
            "tmp/report.json",
            ".scannerwork/task.txt",
            "docs/.DS_Store",
            "logs/debug.trace",
            "coverage.xml",
        ],
    ) == [".scannerwork/task.txt", "coverage.xml", "docs/.DS_Store", "logs/debug.trace", "tmp/report.json"]


def test_phi_filename_findings_flag_structural_and_name_tokens() -> None:
    policy = {
        "phi_filename": {
            "structural_patterns": [
                r"(?<![a-z0-9])mrn[ _\-]?\d",
                r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)",
                r"patient[ _\-]?(name|id|mrn)",
                r"(?<![a-z0-9])accession[ _\-]?(#|\d)",
                r"(?<![a-z0-9])acc[ _\-]?(#|\d{5,})",
            ],
            "name_tokens": ["john", "smith"],
            "allowlist_patterns": [],
        }
    }

    # Build the SSN-format token at runtime so no SSN-shaped literal appears in
    # source (the repo's sensitive-content gate would flag it as US_SSN).
    ssn_name = Path("fixtures", f"ssn_{'-'.join(('123', '45', '6789'))}.txt").as_posix()

    findings = phi_filename_findings(
        policy,
        [
            "src/guiskindose/beam_class.py",
            "exports/MRN_00123_rdsr.dcm",
            "data/john_smith_case.csv",
            "cases/patient_name_list.xlsx",
            ssn_name,
            "exports/acc-987654321.json",
        ],
    )

    assert findings == [
        "cases/patient_name_list.xlsx",
        "data/john_smith_case.csv",
        "exports/MRN_00123_rdsr.dcm",
        "exports/acc-987654321.json",
        ssn_name,
    ]


def test_phi_filename_findings_respect_allowlist_and_word_boundaries() -> None:
    policy = {
        "phi_filename": {
            "structural_patterns": [r"(?<![a-z0-9])mrn[ _\-]?\d"],
            "name_tokens": ["mark"],
            "allowlist_patterns": ["docs/contributors/mark_bio.md"],
        }
    }

    # "mark" only matches as a whole token, not inside "watermark"/"benchmark";
    # the allowlisted path is exempt even though it contains a name token.
    assert phi_filename_findings(
        policy,
        [
            "src/plotting/watermark.py",
            "tests/benchmark_dose.py",
            "docs/contributors/mark_bio.md",
        ],
    ) == []


def test_phi_filename_allowlist_is_case_insensitive_on_every_os() -> None:
    # A mixed-case allowlist glob must exempt a differently-cased path
    # deterministically, regardless of the host filesystem's case sensitivity.
    policy = {
        "phi_filename": {
            "structural_patterns": [],
            "name_tokens": ["mark"],
            "allowlist_patterns": ["docs/Contributors/Mark_*.md"],
        }
    }

    assert phi_filename_findings(policy, ["docs/contributors/mark_bio.md"]) == []
    # A non-allowlisted name-token path is still flagged.
    assert phi_filename_findings(policy, ["data/mark_case.csv"]) == ["data/mark_case.csv"]


def test_repository_policy_blocks_phi_like_filenames() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = json.loads((root / "dev-docs/privacy_admission_policy.json").read_text(encoding="utf-8"))

    flagged = phi_filename_findings(
        policy,
        ["exports/MRN_9981_rdsr.dcm", "data/anna_garcia_events.csv"],
    )

    assert flagged == ["data/anna_garcia_events.csv", "exports/MRN_9981_rdsr.dcm"]


def test_repository_policy_accession_floor_ignores_year_tags() -> None:
    # The 'acc' abbreviation uses a 5-digit floor so year-tag fixtures like
    # acc-2024 do not false-positive, while the unambiguous full word
    # 'accession' keeps a 1-digit floor and long accession runs still block.
    root = Path(__file__).resolve().parents[2]
    policy = json.loads((root / "dev-docs/privacy_admission_policy.json").read_text(encoding="utf-8"))

    flagged = phi_filename_findings(
        policy,
        [
            "reports/acc-2024_summary.csv",  # year tag -> not PHI
            "reports/access_log.txt",  # abbreviation collision -> not PHI
            "exports/acc-987654321.dcm",  # long accession run -> PHI
            "exports/accession-42.dcm",  # unambiguous keyword -> PHI
        ],
    )

    assert flagged == ["exports/acc-987654321.dcm", "exports/accession-42.dcm"]


def test_repository_policy_name_tokens_scan_directory_components() -> None:
    # Deliberate design: name tokens are matched over the whole path, not just
    # the basename, so a patient name embedded in a directory (common in
    # imaging exports) still blocks. See phi_filename._comment in the policy.
    root = Path(__file__).resolve().parents[2]
    policy = json.loads((root / "dev-docs/privacy_admission_policy.json").read_text(encoding="utf-8"))

    assert phi_filename_findings(policy, ["patients/anna_garcia/scan.dcm"]) == ["patients/anna_garcia/scan.dcm"]


def test_route_requires_matching_extension_prefix_and_diff_signal() -> None:
    rule = ScannerRule(
        scanner_id="hounddog",
        version="test",
        trigger_extensions=frozenset({".py"}),
        trigger_prefixes=("src/",),
        diff_regex=r"(?i)logger",
        input_extensions=frozenset({".py"}),
        input_prefixes=("src/",),
        scope="all_matching",
        config_paths=(),
    )

    assert required_rules([rule], ["src/app.py"], "+ logger.info(value)") == [rule]
    assert required_rules([rule], ["tests/test_app.py"], "+ logger.info(value)") == []
    assert required_rules([rule], ["src/app.py"], "+ return value") == []


def test_input_digest_is_order_independent_and_does_not_contain_paths() -> None:
    first = digest_mapping({"src/a.py": "abc", "src/b.py": "def"})
    second = digest_mapping({"src/b.py": "def", "src/a.py": "abc"})

    assert first == second
    assert "src" not in first
    assert len(first) == 64


def test_repository_policy_json_has_unique_scanner_ids() -> None:
    root = Path(__file__).resolve().parents[2]
    policy = json.loads((root / "dev-docs/privacy_admission_policy.json").read_text(encoding="utf-8"))
    scanner_ids = [item["id"] for item in policy["scanners"]]

    assert len(scanner_ids) == len(set(scanner_ids))
    assert policy["receipt_max_age_hours"] > 0


def test_staged_policy_check_cannot_be_bypassed_by_restoring_worktree_ignore(tmp_path: Path) -> None:
    initialize_policy_repository(tmp_path)
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    git(tmp_path, "add", ".gitignore")
    (tmp_path / ".gitignore").write_text("tmp/\n", encoding="utf-8")

    assert command_check(tmp_path, "staged") == 1


def test_staged_policy_check_rejects_force_added_ignored_output(tmp_path: Path) -> None:
    initialize_policy_repository(tmp_path)
    output = tmp_path / "tmp" / "report.json"
    output.parent.mkdir()
    output.write_text("synthetic", encoding="utf-8")
    git(tmp_path, "add", "-f", "tmp/report.json")

    assert command_check(tmp_path, "staged") == 1


def test_receipt_expiry_and_configuration_mismatch_fail_closed(tmp_path: Path) -> None:
    initialize_policy_repository(tmp_path)
    expected = {
        "schema_version": 1,
        "scanner_id": "presidio",
        "scanner_policy_version": "test",
        "tool_version_sha256": "tool",
        "policy_config_sha256": "config",
        "input_sha256": "input",
        "input_count": 1,
        "status": "clean",
    }
    target = receipt_path(tmp_path, "presidio", "input")
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps({**expected, "completed_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}),
        encoding="utf-8",
    )

    assert verify_receipt(tmp_path, expected, 1) == "expired"

    target.write_text(
        json.dumps({**expected, "completed_at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    assert verify_receipt(tmp_path, expected, 1) is None
    assert verify_receipt(tmp_path, {**expected, "policy_config_sha256": "changed"}, 1) == "mismatch_policy_config_sha256"
