#!/usr/bin/env python3
"""Check tracked content and opaque assets for accidental sensitive-data exposure.

The checker is intentionally conservative:

* direct PII/PHI-like text and absolute local paths are errors;
* images, DICOM, opaque binary files, and extensionless files must have an
  exact-hash entry in ``dev-docs/approved_asset_inventory.json``;
* existing assets may be recorded as ``pending`` during the one-time manual
  baseline review, but a new or changed asset always fails; and
* diagnostics never include a matched value. This makes the check safe to run
  in local hooks and CI logs.

It is a repository-admission control, not a claim of HIPAA or DICOM-profile
compliance. In particular, a DICOM header check cannot prove that pixels lack
burned-in text; that requires the recorded manual review in the inventory.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

try:
    import pydicom
except ImportError:  # pragma: no cover - pydicom is a core project dependency.
    pydicom = None  # type: ignore[assignment]


INVENTORY_RELATIVE_PATH = Path("dev-docs/approved_asset_inventory.json")
ALLOWLIST_RELATIVE_PATH = Path("dev-docs/sensitive_content_allowlist.json")
INVENTORY_VERSION = 1

ASSET_SUFFIXES = {
    ".avif",
    ".bmp",
    ".dcm",
    ".dicom",
    ".gif",
    ".heic",
    ".ico",
    ".jpeg",
    ".jpg",
    ".npy",
    ".npz",
    ".pdf",
    ".png",
    ".stl",
    ".svg",
    ".tif",
    ".tiff",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
    ".xlsx",
    ".zip",
}

TEXTUAL_ARCHIVE_SUFFIXES = {".xlsx"}
DIRECT_IDENTIFIER_KEYWORDS = {
    "AccessionNumber",
    "InstitutionAddress",
    "InstitutionName",
    "InstitutionalDepartmentName",
    "OperatorsName",
    "OtherPatientIDs",
    "OtherPatientNames",
    "PatientAddress",
    "PatientBirthDate",
    "PatientBirthTime",
    "PatientID",
    "PatientMotherBirthName",
    "PatientName",
    "PatientSex",
    "PatientTelephoneNumbers",
    "PerformingPhysicianName",
    "PhysiciansOfRecord",
    "ReferringPhysicianName",
    "StationName",
}

SENSITIVE_PATTERNS = (
    (
        "EMAIL_ADDRESS",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@(?!example\.(?:com|org|net)\b)[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    ),
    ("US_SSN", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("US_PHONE_NUMBER", re.compile(r"(?<!\d)(?:\+1[-. ]?)?(?:\(?\d{3}\)?[-. ]?)\d{3}[-. ]\d{4}(?!\d)")),
    (
        "POSIX_HOME_PATH",
        re.compile(r"(?<![A-Za-z0-9_./-])/(?:Users|home)/[^\s)>`\"']+"),
    ),
    (
        "MACOS_TEMP_PATH",
        re.compile(r"(?<![A-Za-z0-9_./-])/private/(?:var|tmp)/[^\s)>`\"']+"),
    ),
    ("WINDOWS_USER_PATH", re.compile(r"(?i)(?<![A-Za-z0-9_])(?:[A-Z]:\\\\Users\\\\)[^\s)>`\"']+")),
    ("FILE_URI", re.compile(r"(?i)file:///(?:Users|home|private|var)/[^\s)>`\"']+")),
)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    level: str
    location: str = ""

    def render(self) -> str:
        suffix = f":{self.location}" if self.location else ""
        return f"{self.level.upper()} {self.path}{suffix}: {self.rule}"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo_root, capture_output=True, check=False)


def tracked_paths(repo_root: Path) -> list[str]:
    result = _run_git(repo_root, "ls-files", "-z")
    if result.returncode:
        raise RuntimeError("git ls-files failed")
    return sorted(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)


def normalize_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_extensionless(path: str) -> bool:
    name = PurePosixPath(path).name
    return not Path(name).suffix


def is_probably_binary(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:8192]
    except OSError:
        return True
    if b"\0" in sample:
        return True
    try:
        # The fixed-size sample can end mid-character; an incremental decoder
        # accepts that incomplete final sequence while still rejecting invalid UTF-8.
        codecs.getincrementaldecoder("utf-8")().decode(sample, final=False)
    except UnicodeDecodeError:
        return True
    return False


def asset_kind(path: str, full_path: Path) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in {".dcm", ".dicom"}:
        return "dicom"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg", ".heic", ".avif"}:
        return "image"
    if suffix in ASSET_SUFFIXES or is_probably_binary(full_path):
        return "opaque_binary"
    if is_extensionless(path):
        return "extensionless"
    return None


def load_json(path: Path, expected_key: str) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path.name}: {exc}") from exc
    if not isinstance(data, dict) or expected_key not in data:
        raise ValueError(f"{path.name} must be a JSON object containing {expected_key!r}")
    return data


def load_inventory(path: Path) -> dict[str, dict[str, object]]:
    data = load_json(path, "assets")
    if data.get("version") != INVENTORY_VERSION or not isinstance(data["assets"], list):
        raise ValueError(f"{path.name} has an unsupported format")
    entries: dict[str, dict[str, object]] = {}
    for item in data["assets"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"{path.name} contains an invalid asset entry")
        rel_path = normalize_path(item["path"])
        if rel_path in entries:
            raise ValueError(f"{path.name} contains duplicate path {rel_path!r}")
        entries[rel_path] = item
    return entries


def load_allowlist(path: Path) -> set[tuple[str, str, str]]:
    data = load_json(path, "allowed_findings")
    if data.get("version") != 1 or not isinstance(data["allowed_findings"], list):
        raise ValueError(f"{path.name} has an unsupported format")
    allowed: set[tuple[str, str, str]] = set()
    for item in data["allowed_findings"]:
        if not isinstance(item, dict):
            raise ValueError(f"{path.name} contains an invalid allowlist entry")
        path_value, rule, location = item.get("path"), item.get("rule"), item.get("location")
        if not isinstance(path_value, str) or not isinstance(rule, str) or not isinstance(location, str):
            raise ValueError(f"{path.name} allowlist entries need path, rule, and location strings")
        allowed.add((normalize_path(path_value), rule, location))
    return allowed


def _nonempty_dicom_identifiers(path: Path) -> tuple[list[str], bool]:
    """Return keyword-only DICOM identifiers and whether private values exist."""
    if pydicom is None:
        return [], False
    try:
        dataset = pydicom.dcmread(path, stop_before_pixels=True, force=False)
    except Exception:
        return [], False
    identifiers: list[str] = []
    private_values = False
    for element in dataset.iterall():
        value = str(element.value).strip() if element.value is not None else ""
        if element.tag.is_private and value:
            private_values = True
        if element.keyword in DIRECT_IDENTIFIER_KEYWORDS and value:
            identifiers.append(element.keyword)
    return sorted(set(identifiers)), private_values


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _xlsx_text(path: Path) -> Iterable[tuple[str, str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith((".xml", ".rels")):
                    continue
                try:
                    yield name, archive.read(name).decode("utf-8")
                except (KeyError, UnicodeDecodeError):
                    continue
    except zipfile.BadZipFile:
        return


def _text_findings(path: str, text: str, location_prefix: str = "") -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in SENSITIVE_PATTERNS:
            if pattern.search(line):
                location = f"{location_prefix}{line_number}" if location_prefix else str(line_number)
                findings.append(Finding(path=path, rule=rule, level="error", location=location))
    return findings


def _approved_dicom_review(entry: dict[str, object]) -> bool:
    review = entry.get("dicom_review")
    return isinstance(review, dict) and all(
        review.get(name) is True
        for name in ("direct_identifiers_reviewed", "private_tags_reviewed", "burned_in_text_reviewed")
    )


def run_checks(
    repo_root: Path,
    *,
    paths: Sequence[str] | None = None,
    require_approved_assets: bool = False,
) -> list[Finding]:
    inventory = load_inventory(repo_root / INVENTORY_RELATIVE_PATH)
    allowlist = load_allowlist(repo_root / ALLOWLIST_RELATIVE_PATH)
    tracked = [normalize_path(path) for path in (paths if paths is not None else tracked_paths(repo_root))]
    findings: list[Finding] = []
    assets_seen: set[str] = set()

    for rel_path in tracked:
        full_path = repo_root / rel_path
        if not full_path.is_file():
            findings.append(Finding(rel_path, "TRACKED_FILE_MISSING", "error"))
            continue
        kind = asset_kind(rel_path, full_path)
        entry = inventory.get(rel_path)
        if kind is not None:
            assets_seen.add(rel_path)
            if entry is None:
                findings.append(Finding(rel_path, "ASSET_NOT_IN_APPROVED_INVENTORY", "error"))
            elif entry.get("sha256") != sha256(full_path):
                findings.append(Finding(rel_path, "ASSET_HASH_NOT_APPROVED", "error"))
            else:
                review = entry.get("review")
                status = review.get("status") if isinstance(review, dict) else None
                if status != "approved":
                    level = "error" if require_approved_assets else "warning"
                    findings.append(Finding(rel_path, "ASSET_MANUAL_REVIEW_PENDING", level))
                elif kind == "dicom" and not _approved_dicom_review(entry):
                    findings.append(Finding(rel_path, "DICOM_REVIEW_FIELDS_INCOMPLETE", "error"))

            if kind == "dicom":
                identifiers, private_values = _nonempty_dicom_identifiers(full_path)
                if identifiers:
                    findings.append(Finding(rel_path, "DICOM_DIRECT_IDENTIFIER_FIELDS_PRESENT", "warning"))
                if private_values:
                    findings.append(Finding(rel_path, "DICOM_PRIVATE_TAG_VALUES_PRESENT", "warning"))

        text = _read_text(full_path)
        if text is not None:
            findings.extend(_text_findings(rel_path, text))
        if Path(rel_path).suffix.lower() in TEXTUAL_ARCHIVE_SUFFIXES:
            for member_name, member_text in _xlsx_text(full_path):
                findings.extend(_text_findings(rel_path, member_text, f"{member_name}:"))

    for rel_path in sorted(set(inventory) - assets_seen):
        findings.append(Finding(rel_path, "INVENTORY_ENTRY_NOT_A_TRACKED_ASSET", "error"))

    return sorted(
        (finding for finding in findings if (finding.path, finding.rule, finding.location) not in allowlist),
        key=lambda finding: (finding.path, finding.location, finding.rule),
    )


def inventory_template(repo_root: Path, paths: Sequence[str] | None = None) -> dict[str, object]:
    tracked = [normalize_path(path) for path in (paths if paths is not None else tracked_paths(repo_root))]
    assets: list[dict[str, object]] = []
    for rel_path in tracked:
        full_path = repo_root / rel_path
        if not full_path.is_file():
            continue
        kind = asset_kind(rel_path, full_path)
        if kind is None:
            continue
        entry: dict[str, object] = {
            "path": rel_path,
            "sha256": sha256(full_path),
            "kind": kind,
            "purpose": "TODO: document why this tracked asset is required",
            "review": {"status": "pending", "reviewer": None, "reviewed_on": None},
        }
        if kind == "dicom":
            entry["dicom_review"] = {
                "direct_identifiers_reviewed": False,
                "private_tags_reviewed": False,
                "burned_in_text_reviewed": False,
            }
        assets.append(entry)
    return {"version": INVENTORY_VERSION, "assets": assets}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root_from_script())
    parser.add_argument(
        "--require-approved-assets",
        action="store_true",
        help="Fail instead of warn for baseline assets awaiting a human review.",
    )
    parser.add_argument(
        "--print-inventory-template",
        action="store_true",
        help="Print a hash-pinned pending-review inventory template and exit.",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if args.print_inventory_template:
        print(json.dumps(inventory_template(repo_root), indent=2) + "\n")
        return 0
    try:
        findings = run_checks(repo_root, require_approved_assets=args.require_approved_assets)
    except (RuntimeError, ValueError) as exc:
        print(f"check_sensitive_content: {exc}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.render(), file=sys.stderr)
    errors = [finding for finding in findings if finding.level == "error"]
    if errors:
        return 1
    print("Sensitive-content gate OK (pending asset reviews reported as warnings).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
