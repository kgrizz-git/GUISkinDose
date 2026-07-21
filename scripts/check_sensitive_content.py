#!/usr/bin/env python3
"""Check tracked content and opaque assets for accidental sensitive-data exposure.

The checker is intentionally conservative:

* direct PII/PHI-like text and absolute local paths are errors;
* images, rendered notebook visuals, DICOM, and opaque binary files must have
  an exact-hash entry in
  ``dev-docs/approved_asset_inventory.json``;
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
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

try:
    import pydicom
except ImportError:  # pragma: no cover - pydicom is a core project dependency.
    pydicom = None  # type: ignore[assignment]

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - verified by a fail-closed finding below.
    PdfReader = None  # type: ignore[assignment,misc]

if __package__:
    from .check_sensitive_helpers import (
        BZIP2_CONTAINER_SUFFIXES,
        DICOM_SUFFIX,
        GZIP_CONTAINER_SUFFIXES,
        OFFICE_CONTAINER_SUFFIXES,
        POSTSCRIPT_SUFFIXES,
        TAR_CONTAINER_SUFFIXES,
        XZ_CONTAINER_SUFFIXES,
        ZIP_CONTAINER_SUFFIXES,
        ContainerReadError,
        cell_data_mappings,
        extract_pdf_attachments,  # noqa: F401 - re-exported for callers/tests.
        extract_pdf_metadata,  # noqa: F401 - re-exported for callers/tests.
        extract_pdf_page_text,  # noqa: F401 - re-exported for callers/tests.
        inspect_container_member,
        iter_container_members,
        mapping_has_visual_mime,
        pdf_reader_text,
    )
else:  # pragma: no cover - exercised by running this file directly.
    from check_sensitive_helpers import (
        BZIP2_CONTAINER_SUFFIXES,
        DICOM_SUFFIX,
        GZIP_CONTAINER_SUFFIXES,
        OFFICE_CONTAINER_SUFFIXES,
        POSTSCRIPT_SUFFIXES,
        TAR_CONTAINER_SUFFIXES,
        XZ_CONTAINER_SUFFIXES,
        ZIP_CONTAINER_SUFFIXES,
        ContainerReadError,
        cell_data_mappings,
        extract_pdf_attachments,  # noqa: F401 - re-exported for callers/tests.
        extract_pdf_metadata,  # noqa: F401 - re-exported for callers/tests.
        extract_pdf_page_text,  # noqa: F401 - re-exported for callers/tests.
        inspect_container_member,
        iter_container_members,
        mapping_has_visual_mime,
        pdf_reader_text,
    )


INVENTORY_RELATIVE_PATH = Path("dev-docs/approved_asset_inventory.json")
ALLOWLIST_RELATIVE_PATH = Path("dev-docs/sensitive_content_allowlist.json")
INVENTORY_VERSION = 1

ASSET_SUFFIXES = {
    ".avif",
    ".bmp",
    ".dcm",
    DICOM_SUFFIX,
    ".gif",
    ".heic",
    ".ico",
    ".jpeg",
    ".jpg",
    ".doc",
    ".npy",
    ".npz",
    ".png",
    ".eps",
    ".ps",
    ".stl",
    ".svg",
    ".tif",
    ".tiff",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsb",
    ".xlsm",
}

CONTAINER_KINDS = {"archive", "office_document"}
DIAGNOSTIC_ARTIFACT_SUFFIXES = {".cache", ".err", ".log", ".out", ".pkl", ".pickle", ".trace"}
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
    (
        "US_PHONE_NUMBER",
        re.compile(
            r"(?<![0-9A-Fa-f-])(?:\+?1[-. ]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[-. ]?"
            r"[2-9]\d{2}[-. ]\d{4}(?![0-9A-Fa-f-])"
        ),
    ),
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
    (
        "PRIVATE_IPV4_ADDRESS",
        re.compile(
            r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|192\.168(?:\.\d{1,3}){2})(?![\d.])"
        ),
    ),
    (
        # Unique-local (fc/fd leading octet; fc00 through fdff) and link-local
        # (fe80 through febf) IPv6 addresses. Requires the private prefix hextet plus
        # >=2 colon groups so a bare hex label or MAC address (colon after only two hex
        # digits) does not match. Prefixes are written without a trailing "::" here so
        # this definition does not flag itself.
        "PRIVATE_IPV6_ADDRESS",
        re.compile(r"(?i)(?<![0-9a-f:])(?:f[cd][0-9a-f]{2}|fe[89ab][0-9a-f])(?::[0-9a-f]{0,4}){2,}(?![0-9a-f:])"),
    ),
    ("DICOM_PACS_URI", re.compile(r"(?i)\b(?:dicom|pacs)://[^\s)>`\"']+")),
    (
        "INTERNAL_DICOM_PACS_HOST",
        re.compile(
            r"(?i)\b(?:dicom|pacs)(?:[_-]?(?:host|server|url))?\s*[:=]\s*['\"]?"
            r"[a-z0-9-]+(?:\.(?:local|internal|corp|lan))(?::\d{1,5})?"
        ),
    ),
    (
        "CONTEXTUAL_PATIENT_IDENTIFIER",
        re.compile(
            r"(?i)\b(?:mrn|medical[_ -]?record[_ -]?number|patient[_ -]?id|accession(?:[_ -]?number)?|"
            r"study[_ -]?id|procedure[_ -]?id)\s*[:=]\s*['\"]?(?!anonymous\b|test\b|phantom\b)"
            r"(?=[a-z0-9-]*\d)[a-z0-9-]+"
        ),
    ),
)

ESCAPED_FASTAPI_DECORATOR_EMAILS = frozenset(
    f"n@app.{method}"
    for method in ("route", "get", "post", "put", "delete", "patch", "options", "head", "trace", "middleware")
)

SENSITIVE_PATH_PATTERNS = (
    (
        "SENSITIVE_PATIENT_PATH",
        re.compile(r"(?i)(?:^|[._-])patient(?:[._-]?(?:id|name|mrn))?[._-]?[a-z]*\d{2,}(?:[._-]|$)"),
    ),
    (
        "SENSITIVE_MRN_PATH",
        re.compile(r"(?i)(?:^|[._-])mrn[._-]?[a-z]*\d{2,}(?:[._-]|$)"),
    ),
    (
        "SENSITIVE_ACCESSION_PATH",
        re.compile(r"(?i)(?:^|[._-])accession[._-]?[a-z]*\d{2,}(?:[._-]|$)"),
    ),
    (
        "SENSITIVE_STUDY_PATH",
        re.compile(r"(?i)(?:^|[._-])study(?:[._-]?id)?[._-]?[a-z]*\d{2,}(?:[._-]|$)"),
    ),
)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    level: str
    location: str = ""

    def render(self, *, verbose_paths: bool = False) -> str:
        suffix = f":{self.location}" if self.location else ""
        if verbose_paths:
            path_label = self.path
        else:
            token = hashlib.sha256(normalize_path(self.path).encode("utf-8")).hexdigest()[:12]
            path_label = f"path_token={token}"
        return f"{self.level.upper()} {path_label}{suffix}: {self.rule}"


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


def has_dicom_preamble(path: Path) -> bool:
    """Return whether *path* has the standard DICOM ``DICM`` preamble marker."""
    try:
        with path.open("rb") as source:
            return source.read(132)[128:132] == b"DICM"
    except OSError:
        return False


def is_diagnostic_artifact(path: str) -> bool:
    """Return whether a filename is a high-risk transient diagnostic artifact."""
    name = PurePosixPath(path).name.lower()
    return Path(name).suffix in DIAGNOSTIC_ARTIFACT_SUFFIXES or bool(re.search(r"\.log\.\d+$", name))


def has_notebook_embedded_visual_output(path: Path) -> bool:
    """Return whether a notebook embeds a rendered image or PDF output/attachment.

    Delegates cell parsing to ``cell_data_mappings``/``mapping_has_visual_mime``
    (``check_sensitive_helpers``); this function only owns reading and
    validating the top-level notebook JSON shape.
    """
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        return False
    return any(mapping_has_visual_mime(data) for cell in notebook["cells"] for data in cell_data_mappings(cell))


def is_probably_binary(path: Path) -> bool:
    """Return whether the complete file is not valid, NUL-free UTF-8 text."""
    try:
        data = path.read_bytes()
    except OSError:
        return True
    if b"\0" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def asset_kind(path: str, full_path: Path) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix in {".dcm", DICOM_SUFFIX} or has_dicom_preamble(full_path):
        return "dicom"
    if suffix in OFFICE_CONTAINER_SUFFIXES:
        return "office_document"
    if (
        suffix
        in ZIP_CONTAINER_SUFFIXES
        | TAR_CONTAINER_SUFFIXES
        | GZIP_CONTAINER_SUFFIXES
        | BZIP2_CONTAINER_SUFFIXES
        | XZ_CONTAINER_SUFFIXES
    ):
        return "archive"
    if suffix == ".pdf":
        return "pdf"
    if suffix in POSTSCRIPT_SUFFIXES:
        return "postscript"
    if suffix == ".ipynb" and has_notebook_embedded_visual_output(full_path):
        return "notebook_embedded_visual"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg", ".heic", ".avif"}:
        return "image"
    if suffix in ASSET_SUFFIXES or is_probably_binary(full_path):
        return "opaque_binary"
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


def _pdf_text(path: Path) -> tuple[list[tuple[str, str]], str | None]:
    """Return extractable PDF text and a fail-closed scanner error, if any.

    PDF page text, document metadata, and unencrypted embedded attachments are
    scanned. Rendered pages still require a manual inventory review because
    extraction cannot establish whether an image has burned-in information.

    Reader construction, the encryption check, and exception handling stay
    here (rather than in ``check_sensitive_helpers``) so tests can monkeypatch
    this module's ``PdfReader`` symbol; the actual field extraction is
    delegated to ``pdf_reader_text``.
    """
    if PdfReader is None:
        return [], "PDF_TEXT_SCANNER_UNAVAILABLE"
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and reader.decrypt("") == 0:
            return [], "PDF_TEXT_EXTRACTION_FAILED"
        return pdf_reader_text(reader), None
    except Exception:
        return [], "PDF_TEXT_EXTRACTION_FAILED"


def _postscript_text(path: Path) -> str | None:
    """Decode PostScript conservatively so ASCII strings survive embedded binary data."""
    try:
        return path.read_bytes().decode("latin-1")
    except OSError:
        return None


def _container_text(path: Path) -> tuple[list[tuple[str, str]], set[str], str | None]:
    """Extract bounded text from supported container members without writing them to disk.

    Delegates member iteration and bounded reads to ``iter_container_members``
    and per-member inspection to ``inspect_container_member`` (both in
    ``check_sensitive_helpers``); this function only owns aggregating results
    and computing the privacy-sensitive-name flag via ``sensitive_path_rule``,
    which must stay in this module.
    """
    extracted: list[tuple[str, str]] = []
    flags: set[str] = set()
    for member_number, item in enumerate(iter_container_members(path), start=1):
        if isinstance(item, ContainerReadError):
            return extracted, flags, item.code
        name, data = item
        member_text, member_flags, member_error = inspect_container_member(
            member_number, name, data, name_is_sensitive=sensitive_path_rule(name) is not None
        )
        if member_error:
            return extracted, flags, member_error
        extracted.extend(member_text)
        flags.update(member_flags)
    return extracted, flags, None


def _is_escaped_fastapi_decorator_email(line: str, match: re.Match[str]) -> bool:
    """Avoid treating an escaped ``\\n@app.post``-style decorator as an email address."""
    return (
        match.start() > 0
        and line[match.start() - 1] == "\\"
        and match.group(0).lower() in ESCAPED_FASTAPI_DECORATOR_EMAILS
    )


def text_findings(path: str, text: str, location_prefix: str = "") -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in SENSITIVE_PATTERNS:
            match = pattern.search(line)
            if match and not (rule == "EMAIL_ADDRESS" and _is_escaped_fastapi_decorator_email(line, match)):
                location = f"{location_prefix}{line_number}" if location_prefix else str(line_number)
                findings.append(Finding(path=path, rule=rule, level="error", location=location))
    return findings


def sensitive_path_rule(path: str) -> str | None:
    """Return a rule for a PHI-like path component without returning its value."""
    for component in PurePosixPath(normalize_path(path)).parts:
        for rule, pattern in SENSITIVE_PATH_PATTERNS:
            if pattern.search(component):
                return rule
    return None


def _approved_dicom_review(entry: dict[str, object]) -> bool:
    review = entry.get("dicom_review")
    return isinstance(review, dict) and all(
        review.get(name) is True
        for name in ("direct_identifiers_reviewed", "private_tags_reviewed", "burned_in_text_reviewed")
    )


def _approved_container_review(entry: dict[str, object]) -> bool:
    review = entry.get("container_review")
    return isinstance(review, dict) and all(
        review.get(name) is True
        for name in ("embedded_files_reviewed", "embedded_images_reviewed", "embedded_dicom_reviewed")
    )


def _tracked_path_findings(rel_path: str, full_path: Path) -> tuple[list[Finding], bool]:
    """Return path-level findings and whether the caller should skip content scanning.

    Covers the sensitive-path-component check, the missing-file check (which
    short-circuits everything else for that path), and the diagnostic-artifact
    check.
    """
    findings: list[Finding] = []
    if path_rule := sensitive_path_rule(rel_path):
        findings.append(Finding(rel_path, path_rule, "error"))
    if not full_path.is_file():
        findings.append(Finding(rel_path, "TRACKED_FILE_MISSING", "error"))
        return findings, True
    if is_diagnostic_artifact(rel_path):
        findings.append(Finding(rel_path, "DIAGNOSTIC_ARTIFACT_FORBIDDEN", "error"))
    return findings, False


def _asset_inventory_findings(
    rel_path: str,
    full_path: Path,
    kind: str,
    entry: dict[str, object] | None,
    require_approved_assets: bool,
) -> list[Finding]:
    """Return the single most relevant approved-asset-inventory finding, if any."""
    if entry is None:
        return [Finding(rel_path, "ASSET_NOT_IN_APPROVED_INVENTORY", "error")]
    if entry.get("sha256") != sha256(full_path):
        return [Finding(rel_path, "ASSET_HASH_NOT_APPROVED", "error")]
    if entry.get("kind") != kind:
        return [Finding(rel_path, "ASSET_INVENTORY_KIND_MISMATCH", "error")]
    review = entry.get("review")
    status = review.get("status") if isinstance(review, dict) else None
    if status != "approved":
        level = "error" if require_approved_assets else "warning"
        return [Finding(rel_path, "ASSET_MANUAL_REVIEW_PENDING", level)]
    if kind == "dicom" and not _approved_dicom_review(entry):
        return [Finding(rel_path, "DICOM_REVIEW_FIELDS_INCOMPLETE", "error")]
    if kind in CONTAINER_KINDS and not _approved_container_review(entry):
        return [Finding(rel_path, "CONTAINER_REVIEW_FIELDS_INCOMPLETE", "error")]
    return []


def _dicom_identifier_findings(rel_path: str, full_path: Path) -> list[Finding]:
    """Return warnings for non-empty direct-identifier keywords and private tag values."""
    identifiers, private_values = _nonempty_dicom_identifiers(full_path)
    findings: list[Finding] = []
    if identifiers:
        findings.append(Finding(rel_path, "DICOM_DIRECT_IDENTIFIER_FIELDS_PRESENT", "warning"))
    if private_values:
        findings.append(Finding(rel_path, "DICOM_PRIVATE_TAG_VALUES_PRESENT", "warning"))
    return findings


def _pdf_scan_findings(rel_path: str, full_path: Path) -> list[Finding]:
    """Return findings from scanning a PDF's extractable metadata/page/attachment text."""
    findings: list[Finding] = []
    pdf_text, pdf_error = _pdf_text(full_path)
    if pdf_error:
        findings.append(Finding(rel_path, pdf_error, "error"))
    for location_prefix, extracted_text in pdf_text:
        findings.extend(text_findings(rel_path, extracted_text, location_prefix))
    return findings


def _postscript_scan_findings(rel_path: str, full_path: Path) -> list[Finding]:
    """Return findings from scanning a PostScript file's decoded text."""
    postscript_text = _postscript_text(full_path)
    if postscript_text is None:
        return [Finding(rel_path, "POSTSCRIPT_TEXT_EXTRACTION_FAILED", "error")]
    return text_findings(rel_path, postscript_text)


def _container_flag_findings(rel_path: str, flags: set[str]) -> list[Finding]:
    """Return one finding per member-level flag raised during a container scan."""
    flag_rules = {
        "dicom": ("CONTAINER_DICOM_MEMBER_PRESENT", "warning"),
        "nested_container": ("CONTAINER_NESTED_ARCHIVE_PRESENT", "warning"),
        "sensitive_member_name": ("CONTAINER_SENSITIVE_MEMBER_NAME", "error"),
    }
    return [Finding(rel_path, rule, level) for flag, (rule, level) in flag_rules.items() if flag in flags]


def _container_scan_findings(rel_path: str, full_path: Path) -> list[Finding]:
    """Return findings from scanning a container's member text and member-level flags."""
    findings: list[Finding] = []
    container_text, container_flags, container_error = _container_text(full_path)
    if container_error:
        findings.append(Finding(rel_path, container_error, "error"))
    for location_prefix, member_text in container_text:
        findings.extend(text_findings(rel_path, member_text, location_prefix))
    findings.extend(_container_flag_findings(rel_path, container_flags))
    return findings


def _extracted_text_findings(rel_path: str, full_path: Path, kind: str | None) -> list[Finding]:
    """Return findings from plain-text scanning plus the format-specific dispatch.

    Ordinary UTF-8 text is scanned first (matching the historical ordering),
    then exactly one of the PDF, PostScript, or container extractors runs
    based on suffix/kind.
    """
    findings: list[Finding] = []
    text = _read_text(full_path)
    if text is not None:
        findings.extend(text_findings(rel_path, text))
    suffix = Path(rel_path).suffix.lower()
    if suffix == ".pdf":
        findings.extend(_pdf_scan_findings(rel_path, full_path))
    elif suffix in POSTSCRIPT_SUFFIXES:
        findings.extend(_postscript_scan_findings(rel_path, full_path))
    elif kind in CONTAINER_KINDS:
        findings.extend(_container_scan_findings(rel_path, full_path))
    return findings


def _orphan_inventory_findings(inventory: dict[str, dict[str, object]], assets_seen: set[str]) -> list[Finding]:
    """Return a finding for every inventory entry that no longer matches a tracked asset."""
    return [
        Finding(rel_path, "INVENTORY_ENTRY_NOT_A_TRACKED_ASSET", "error")
        for rel_path in sorted(set(inventory) - assets_seen)
    ]


def run_checks(
    repo_root: Path,
    *,
    paths: Sequence[str] | None = None,
    require_approved_assets: bool = False,
) -> list[Finding]:
    """Scan tracked paths and return sorted, allowlist-filtered findings.

    Orchestrates (in order, per path): path/diagnostic checks, approved-asset
    inventory policy, DICOM identifier warnings, and extracted-text scanning
    (plain text, then PDF/PostScript/container dispatch) — see the ``_*``
    policy helpers above for each stage's rules.
    """
    inventory = load_inventory(repo_root / INVENTORY_RELATIVE_PATH)
    allowlist = load_allowlist(repo_root / ALLOWLIST_RELATIVE_PATH)
    tracked = [normalize_path(path) for path in (paths if paths is not None else tracked_paths(repo_root))]
    findings: list[Finding] = []
    assets_seen: set[str] = set()

    for rel_path in tracked:
        full_path = repo_root / rel_path
        path_findings, skip_content = _tracked_path_findings(rel_path, full_path)
        findings.extend(path_findings)
        if skip_content:
            continue

        kind = asset_kind(rel_path, full_path)
        entry = inventory.get(rel_path)
        if kind is not None:
            assets_seen.add(rel_path)
            findings.extend(_asset_inventory_findings(rel_path, full_path, kind, entry, require_approved_assets))
            if kind == "dicom":
                findings.extend(_dicom_identifier_findings(rel_path, full_path))

        findings.extend(_extracted_text_findings(rel_path, full_path, kind))

    findings.extend(_orphan_inventory_findings(inventory, assets_seen))

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
        elif kind in CONTAINER_KINDS:
            entry["container_review"] = {
                "embedded_files_reviewed": False,
                "embedded_images_reviewed": False,
                "embedded_dicom_reviewed": False,
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
    parser.add_argument(
        "--verbose-paths",
        action="store_true",
        help="Show repository paths locally; default diagnostics use non-reversible path tokens.",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if args.print_inventory_template:
        print(json.dumps(inventory_template(repo_root), indent=2) + "\n")
        return 0
    try:
        findings = run_checks(repo_root, require_approved_assets=args.require_approved_assets)
    except (RuntimeError, ValueError) as exc:
        print(f"check_sensitive_content: failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding.render(verbose_paths=args.verbose_paths), file=sys.stderr)
    errors = [finding for finding in findings if finding.level == "error"]
    if errors:
        return 1
    print("Sensitive-content gate OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
