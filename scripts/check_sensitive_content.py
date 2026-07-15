#!/usr/bin/env python3
"""Check tracked content and opaque assets for accidental sensitive-data exposure.

The checker is intentionally conservative:

* direct PII/PHI-like text and absolute local paths are errors;
* images, rendered notebook visuals, DICOM, opaque binary files, and
  extensionless files must have an exact-hash entry in
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
import bz2
import codecs
import gzip
import hashlib
import json
import lzma
import re
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
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

POSTSCRIPT_SUFFIXES = {".eps", ".ps"}
OFFICE_CONTAINER_SUFFIXES = {".docx", ".numbers", ".odt", ".ods", ".pages", ".pptx", ".xlsx"}
ZIP_CONTAINER_SUFFIXES = OFFICE_CONTAINER_SUFFIXES | {".epub", ".jar", ".war", ".zip"}
TAR_CONTAINER_SUFFIXES = {".tar", ".tbz", ".tbz2", ".tgz", ".txz"}
GZIP_CONTAINER_SUFFIXES = {".gz", ".gzip"}
BZIP2_CONTAINER_SUFFIXES = {".bz2"}
XZ_CONTAINER_SUFFIXES = {".xz"}
CONTAINER_KINDS = {"archive", "office_document"}
CONTAINER_TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".md",
    ".rels",
    ".rst",
    ".rtf",
    ".tex",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
MAX_CONTAINER_MEMBERS = 2_000
MAX_CONTAINER_MEMBER_BYTES = 16 * 1024 * 1024
MAX_CONTAINER_TOTAL_BYTES = 64 * 1024 * 1024
DIAGNOSTIC_ARTIFACT_SUFFIXES = {".cache", ".err", ".log", ".out", ".pkl", ".pickle", ".trace"}
NOTEBOOK_VISUAL_MIME_TYPES = {"application/pdf"}
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
    (
        "PRIVATE_IPV4_ADDRESS",
        re.compile(r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|192\.168(?:\.\d{1,3}){2})(?![\d.])"),
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
    """Return whether a notebook embeds a rendered image or PDF output/attachment."""
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        return False
    for cell in notebook["cells"]:
        if not isinstance(cell, dict):
            continue
        data_mappings = list(cell.get("attachments", {}).values()) if isinstance(cell.get("attachments"), dict) else []
        outputs = cell.get("outputs", [])
        if isinstance(outputs, list):
            data_mappings.extend(output.get("data", {}) for output in outputs if isinstance(output, dict))
        for data in data_mappings:
            if isinstance(data, dict) and any(
                key.startswith("image/") or key in NOTEBOOK_VISUAL_MIME_TYPES for key in data
            ):
                return True
    return False


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
    if suffix in {".dcm", ".dicom"} or has_dicom_preamble(full_path):
        return "dicom"
    if suffix in OFFICE_CONTAINER_SUFFIXES:
        return "office_document"
    if suffix in ZIP_CONTAINER_SUFFIXES | TAR_CONTAINER_SUFFIXES | GZIP_CONTAINER_SUFFIXES | BZIP2_CONTAINER_SUFFIXES | XZ_CONTAINER_SUFFIXES:
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


def _pdf_text(path: Path | BytesIO) -> tuple[list[tuple[str, str]], str | None]:
    """Return extractable PDF text and a fail-closed scanner error, if any.

    PDF page text, document metadata, and unencrypted embedded attachments are
    scanned. Rendered pages still require a manual inventory review because
    extraction cannot establish whether an image has burned-in information.
    """
    if PdfReader is None:
        return [], "PDF_TEXT_SCANNER_UNAVAILABLE"
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and reader.decrypt("") == 0:
            return [], "PDF_TEXT_EXTRACTION_FAILED"
        extracted: list[tuple[str, str]] = []
        if reader.metadata:
            metadata = "\n".join(f"{key}: {value}" for key, value in reader.metadata.items() if value is not None)
            if metadata:
                extracted.append(("metadata:", metadata))
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                extracted.append((f"page{page_number}:", page_text))
        attachments = getattr(reader, "attachments", {})
        if isinstance(attachments, Mapping):
            for name, contents in attachments.items():
                for attachment_number, content in enumerate(contents, start=1):
                    if isinstance(content, bytes):
                        attachment_text = content.decode("utf-8", errors="ignore")
                        if attachment_text:
                            extracted.append((f"attachment:{name}:{attachment_number}:", attachment_text))
        return extracted, None
    except Exception:
        return [], "PDF_TEXT_EXTRACTION_FAILED"


def _postscript_text(path: Path) -> str | None:
    """Decode PostScript conservatively so ASCII strings survive embedded binary data."""
    try:
        return path.read_bytes().decode("latin-1")
    except OSError:
        return None


def _has_dicom_member(name: str, data: bytes) -> bool:
    return Path(name).suffix.lower() in {".dcm", ".dicom"} or data[128:132] == b"DICM"


def _is_container_member(name: str) -> bool:
    lowered = name.lower()
    return Path(lowered).suffix in (
        ZIP_CONTAINER_SUFFIXES | TAR_CONTAINER_SUFFIXES | GZIP_CONTAINER_SUFFIXES | BZIP2_CONTAINER_SUFFIXES | XZ_CONTAINER_SUFFIXES
    ) or lowered.endswith((".tar.gz", ".tar.bz2", ".tar.xz"))


def _container_member_text(
    member_number: int, name: str, data: bytes
) -> tuple[list[tuple[str, str]], set[str], str | None]:
    """Scan a bounded member without returning its potentially sensitive name."""
    flags: set[str] = set()
    if _has_dicom_member(name, data):
        flags.add("dicom")
    if _is_container_member(name):
        flags.add("nested_container")
    suffix = Path(name).suffix.lower()
    location_prefix = f"member{member_number}:"
    if suffix == ".pdf":
        pdf_text, pdf_error = _pdf_text(BytesIO(data))
        if pdf_error:
            return [], flags, "CONTAINER_PDF_TEXT_EXTRACTION_FAILED"
        return [(f"{location_prefix}{location}", text) for location, text in pdf_text], flags, None
    if suffix in POSTSCRIPT_SUFFIXES:
        return [(location_prefix, data.decode("latin-1"))], flags, None
    if suffix not in CONTAINER_TEXT_SUFFIXES:
        return [], flags, None
    try:
        return [(location_prefix, data.decode("utf-8"))], flags, None
    except UnicodeDecodeError:
        return [], flags, None


def _container_text(path: Path) -> tuple[list[tuple[str, str]], set[str], str | None]:
    """Extract bounded text from supported container members without writing them to disk."""
    member_count = 0
    total_bytes = 0
    extracted: list[tuple[str, str]] = []
    flags: set[str] = set()

    def inspect_member(name: str, data: bytes) -> str | None:
        nonlocal member_count, total_bytes
        member_count += 1
        total_bytes += len(data)
        if member_count > MAX_CONTAINER_MEMBERS or len(data) > MAX_CONTAINER_MEMBER_BYTES or total_bytes > MAX_CONTAINER_TOTAL_BYTES:
            return "CONTAINER_CONTENTS_EXCEED_SCAN_LIMIT"
        member_text, member_flags, member_error = _container_member_text(member_count, name, data)
        extracted.extend(member_text)
        flags.update(member_flags)
        return member_error

    name = path.name.lower()
    try:
        if name.endswith((".tar", ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz", ".tbz2", ".txz")):
            with tarfile.open(path, "r:*") as archive:
                for member in archive:
                    if not member.isfile():
                        continue
                    source = archive.extractfile(member)
                    if source is None:
                        continue
                    error = inspect_member(member.name, source.read(MAX_CONTAINER_MEMBER_BYTES + 1))
                    if error:
                        return extracted, flags, error
        elif Path(name).suffix in ZIP_CONTAINER_SUFFIXES:
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    if member.file_size > MAX_CONTAINER_MEMBER_BYTES:
                        return extracted, flags, "CONTAINER_CONTENTS_EXCEED_SCAN_LIMIT"
                    error = inspect_member(member.filename, archive.read(member))
                    if error:
                        return extracted, flags, error
        elif Path(name).suffix in GZIP_CONTAINER_SUFFIXES:
            with gzip.open(path, "rb") as source:
                error = inspect_member(path.stem, source.read(MAX_CONTAINER_MEMBER_BYTES + 1))
                if error:
                    return extracted, flags, error
        elif Path(name).suffix in BZIP2_CONTAINER_SUFFIXES:
            with bz2.open(path, "rb") as source:
                error = inspect_member(path.stem, source.read(MAX_CONTAINER_MEMBER_BYTES + 1))
                if error:
                    return extracted, flags, error
        elif Path(name).suffix in XZ_CONTAINER_SUFFIXES:
            with lzma.open(path, "rb") as source:
                error = inspect_member(path.stem, source.read(MAX_CONTAINER_MEMBER_BYTES + 1))
                if error:
                    return extracted, flags, error
        else:  # pragma: no cover - asset_kind keeps this branch unreachable.
            return extracted, flags, "CONTAINER_CONTENTS_SCANNER_UNAVAILABLE"
    except (OSError, EOFError, gzip.BadGzipFile, lzma.LZMAError, tarfile.TarError, zipfile.BadZipFile):
        return extracted, flags, "CONTAINER_CONTENTS_EXTRACTION_FAILED"
    return extracted, flags, None


def text_findings(path: str, text: str, location_prefix: str = "") -> list[Finding]:
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


def _approved_container_review(entry: dict[str, object]) -> bool:
    review = entry.get("container_review")
    return isinstance(review, dict) and all(
        review.get(name) is True
        for name in ("embedded_files_reviewed", "embedded_images_reviewed", "embedded_dicom_reviewed")
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
        if is_diagnostic_artifact(rel_path):
            findings.append(Finding(rel_path, "DIAGNOSTIC_ARTIFACT_FORBIDDEN", "error"))

        kind = asset_kind(rel_path, full_path)
        entry = inventory.get(rel_path)
        if kind is not None:
            assets_seen.add(rel_path)
            if entry is None:
                findings.append(Finding(rel_path, "ASSET_NOT_IN_APPROVED_INVENTORY", "error"))
            elif entry.get("sha256") != sha256(full_path):
                findings.append(Finding(rel_path, "ASSET_HASH_NOT_APPROVED", "error"))
            elif entry.get("kind") != kind:
                findings.append(Finding(rel_path, "ASSET_INVENTORY_KIND_MISMATCH", "error"))
            else:
                review = entry.get("review")
                status = review.get("status") if isinstance(review, dict) else None
                if status != "approved":
                    level = "error" if require_approved_assets else "warning"
                    findings.append(Finding(rel_path, "ASSET_MANUAL_REVIEW_PENDING", level))
                elif kind == "dicom" and not _approved_dicom_review(entry):
                    findings.append(Finding(rel_path, "DICOM_REVIEW_FIELDS_INCOMPLETE", "error"))
                elif kind in CONTAINER_KINDS and not _approved_container_review(entry):
                    findings.append(Finding(rel_path, "CONTAINER_REVIEW_FIELDS_INCOMPLETE", "error"))

            if kind == "dicom":
                identifiers, private_values = _nonempty_dicom_identifiers(full_path)
                if identifiers:
                    findings.append(Finding(rel_path, "DICOM_DIRECT_IDENTIFIER_FIELDS_PRESENT", "warning"))
                if private_values:
                    findings.append(Finding(rel_path, "DICOM_PRIVATE_TAG_VALUES_PRESENT", "warning"))

        text = _read_text(full_path)
        if text is not None:
            findings.extend(text_findings(rel_path, text))
        suffix = Path(rel_path).suffix.lower()
        if suffix == ".pdf":
            pdf_text, pdf_error = _pdf_text(full_path)
            if pdf_error:
                findings.append(Finding(rel_path, pdf_error, "error"))
            for location_prefix, extracted_text in pdf_text:
                findings.extend(text_findings(rel_path, extracted_text, location_prefix))
        elif suffix in POSTSCRIPT_SUFFIXES:
            postscript_text = _postscript_text(full_path)
            if postscript_text is None:
                findings.append(Finding(rel_path, "POSTSCRIPT_TEXT_EXTRACTION_FAILED", "error"))
            else:
                findings.extend(text_findings(rel_path, postscript_text))
        elif kind in CONTAINER_KINDS:
            container_text, container_flags, container_error = _container_text(full_path)
            if container_error:
                findings.append(Finding(rel_path, container_error, "error"))
            for location_prefix, member_text in container_text:
                findings.extend(text_findings(rel_path, member_text, location_prefix))
            if "dicom" in container_flags:
                findings.append(Finding(rel_path, "CONTAINER_DICOM_MEMBER_PRESENT", "warning"))
            if "nested_container" in container_flags:
                findings.append(Finding(rel_path, "CONTAINER_NESTED_ARCHIVE_PRESENT", "warning"))

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
