#!/usr/bin/env python3
"""Format-specific readers for the sensitive-content admission gate.

This module owns the low-level, format-specific extraction logic used by
``check_sensitive_content.py``: notebook attachment/output inspection, PDF
text/metadata/attachment extraction, and bounded archive/container member
iteration. It intentionally has no knowledge of the repository's admission
*policy* (inventory rules, allowlists, CLI, or the top-level ``Finding``
model) — that ownership stays in ``check_sensitive_content.py`` so this
module can be imported (and unit tested) independently.

Inputs: file paths (``pathlib.Path``) or in-memory byte strings for notebook,
PDF, and archive/office-document members already selected by the caller.

Outputs: plain data (booleans, lists of ``(location, text)`` tuples, flag
sets, and a small ``ContainerReadError`` sentinel) that the caller turns into
``Finding`` records. No embedded content is ever written to disk or logged;
callers are responsible for keeping raw member names out of diagnostics.

Requirements: no new optional dependencies beyond what ``check_sensitive_content.py``
already declares (``pypdf`` is optional and degrades to a fail-closed error).

Constraint: this module must NOT import from ``check_sensitive_content`` to
avoid a circular import; the two modules communicate only through the
function contracts defined here.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import tarfile
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    # Keeps `reader: PdfReader` a valid type annotation for static analysis even
    # though the runtime symbol below may be rebound to ``None`` when pypdf is
    # unavailable (that rebound value is never used as a type at runtime because
    # `from __future__ import annotations` defers annotation evaluation).
    from pypdf import PdfReader
else:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - verified by a fail-closed finding below.
        PdfReader = None  # type: ignore[assignment,misc]


DICOM_SUFFIX = ".dicom"
POSTSCRIPT_SUFFIXES = {".eps", ".ps"}
OFFICE_CONTAINER_SUFFIXES = {".docx", ".numbers", ".odt", ".ods", ".pages", ".pptx", ".xlsx"}
ZIP_CONTAINER_SUFFIXES = OFFICE_CONTAINER_SUFFIXES | {".epub", ".jar", ".war", ".zip"}
TAR_CONTAINER_SUFFIXES = {".tar", ".tbz", ".tbz2", ".tgz", ".txz"}
GZIP_CONTAINER_SUFFIXES = {".gz", ".gzip"}
BZIP2_CONTAINER_SUFFIXES = {".bz2"}
XZ_CONTAINER_SUFFIXES = {".xz"}
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
NOTEBOOK_VISUAL_MIME_TYPES = {"application/pdf"}


# --------------------------------------------------------------------------
# Notebook attachment/output helpers
# --------------------------------------------------------------------------


def cell_data_mappings(cell: object) -> Iterable[Mapping[str, object]]:
    """Yield MIME-keyed mappings embedded in one Jupyter notebook cell.

    Covers both ``cell["attachments"]`` values and ``cell["outputs"][*]["data"]``
    mappings. Malformed entries (wrong type, missing keys) are silently
    skipped rather than raised, since a single corrupt cell must not crash
    the scan; the caller still requires an approved-inventory entry for any
    notebook it cannot fully parse (see ``asset_kind`` in the main module).
    """
    if not isinstance(cell, dict):
        return
    yield from _attachment_data_mappings(cell)
    yield from _output_data_mappings(cell)


def _attachment_data_mappings(cell: Mapping[str, object]) -> Iterator[Mapping[str, object]]:
    """Yield valid MIME maps from notebook attachments in source order."""
    attachments = cell.get("attachments")
    if isinstance(attachments, dict):
        for value in attachments.values():
            if isinstance(value, Mapping):
                yield value


def _output_data_mappings(cell: Mapping[str, object]) -> Iterator[Mapping[str, object]]:
    """Yield valid MIME maps from notebook outputs in source order."""
    outputs = cell.get("outputs")
    if isinstance(outputs, list):
        for output in outputs:
            if isinstance(output, dict):
                data = output.get("data")
                if isinstance(data, Mapping):
                    yield data


def mapping_has_visual_mime(data: Mapping[str, object]) -> bool:
    """Return whether a MIME-keyed mapping includes a rendered image or PDF."""
    return any(key.startswith("image/") or key in NOTEBOOK_VISUAL_MIME_TYPES for key in data)


# --------------------------------------------------------------------------
# PDF extraction helpers
# --------------------------------------------------------------------------


def extract_pdf_metadata(reader: PdfReader) -> list[tuple[str, str]]:
    """Return document metadata as a single ``("metadata:", text)`` entry, if any."""
    if not reader.metadata:
        return []
    metadata = "\n".join(f"{key}: {value}" for key, value in reader.metadata.items() if value is not None)
    if not metadata:
        return []
    return [("metadata:", metadata)]


def extract_pdf_page_text(reader: PdfReader, page_number: int) -> tuple[str, str] | None:
    """Return one page's extracted text as ``(f"page{page_number}:", text)``, or ``None``."""
    page = reader.pages[page_number - 1]
    page_text = page.extract_text()
    if page_text:
        return (f"page{page_number}:", page_text)
    return None


def extract_pdf_attachments(reader: PdfReader) -> list[tuple[str, str]]:
    """Return decoded text for unencrypted embedded PDF attachments.

    Non-``bytes`` or empty-after-decode attachments are skipped; decoding
    uses ``errors="ignore"`` since attachments are not required to be UTF-8.
    """
    attachments = getattr(reader, "attachments", {})
    if not isinstance(attachments, Mapping):
        return []
    extracted: list[tuple[str, str]] = []
    attachment_index = 0
    for contents in attachments.values():
        for attachment_number, content in enumerate(contents, start=1):
            attachment_index += 1
            if isinstance(content, bytes):
                attachment_text = content.decode("utf-8", errors="ignore")
                if attachment_text:
                    extracted.append((f"attachment{attachment_index}.{attachment_number}:", attachment_text))
    return extracted


def pdf_reader_text(reader: PdfReader) -> list[tuple[str, str]]:
    """Compose metadata, page, and attachment text for an already-opened PDF reader.

    Callers own reader construction and the encryption/exception handling
    (see ``_pdf_text`` in the main module and ``_container_pdf_bytes_text``
    below) so both call sites can apply the same fail-closed rule to their
    own ``PdfReader`` reference without this module needing to import from,
    or be swapped out by, the caller.
    """
    extracted = extract_pdf_metadata(reader)
    for page_number in range(1, len(reader.pages) + 1):
        page_result = extract_pdf_page_text(reader, page_number)
        if page_result:
            extracted.append(page_result)
    extracted.extend(extract_pdf_attachments(reader))
    return extracted


def _container_pdf_bytes_text(data: bytes) -> tuple[list[tuple[str, str]], str | None]:
    """Extract text from a PDF container member using this module's own ``PdfReader``.

    Mirrors the fail-closed rules of the main module's ``_pdf_text`` (missing
    reader, encrypted-and-unopenable document, or any extraction exception
    all yield an error instead of silently skipping the member).
    """
    if PdfReader is None:
        return [], "PDF_TEXT_SCANNER_UNAVAILABLE"
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and reader.decrypt("") == 0:
            return [], "PDF_TEXT_EXTRACTION_FAILED"
        return pdf_reader_text(reader), None
    except Exception:
        return [], "PDF_TEXT_EXTRACTION_FAILED"


# --------------------------------------------------------------------------
# Container (archive/office-document) member helpers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContainerReadError:
    """Terminal item yielded by ``iter_container_members`` on a fail-closed error."""

    code: str


def _has_dicom_member(name: str, data: bytes) -> bool:
    """Return whether a container member looks like a DICOM file by suffix or preamble."""
    return Path(name).suffix.lower() in {".dcm", DICOM_SUFFIX} or data[128:132] == b"DICM"


def _is_container_member(name: str) -> bool:
    """Return whether a container member is itself a supported nested archive."""
    lowered = name.lower()
    return Path(lowered).suffix in (
        ZIP_CONTAINER_SUFFIXES | TAR_CONTAINER_SUFFIXES | GZIP_CONTAINER_SUFFIXES | BZIP2_CONTAINER_SUFFIXES | XZ_CONTAINER_SUFFIXES
    ) or lowered.endswith((".tar.gz", ".tar.bz2", ".tar.xz"))


def inspect_container_member(
    member_number: int, name: str, data: bytes, *, name_is_sensitive: bool = False
) -> tuple[list[tuple[str, str]], set[str], str | None]:
    """Scan one bounded container member without ever returning its raw name.

    ``name_is_sensitive`` is computed by the caller (typically via the main
    module's ``sensitive_path_rule``) so this module never needs to import
    the path-sensitivity policy to flag ``sensitive_member_name``.

    Returns extracted ``(location, text)`` pairs, a set of member-level flags
    (``dicom``, ``nested_container``, ``sensitive_member_name``), and an
    optional fail-closed error code.
    """
    flags: set[str] = set()
    if name_is_sensitive:
        flags.add("sensitive_member_name")
    if _has_dicom_member(name, data):
        flags.add("dicom")
    if _is_container_member(name):
        flags.add("nested_container")
    suffix = Path(name).suffix.lower()
    location_prefix = f"member{member_number}:"
    if suffix == ".pdf":
        pdf_text, pdf_error = _container_pdf_bytes_text(data)
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


def _check_member_limits(member_count: int, total_bytes: int, data: bytes) -> ContainerReadError | None:
    """Return a scan-limit error once member count, member size, or total size is exceeded."""
    if member_count > MAX_CONTAINER_MEMBERS or len(data) > MAX_CONTAINER_MEMBER_BYTES or total_bytes > MAX_CONTAINER_TOTAL_BYTES:
        return ContainerReadError("CONTAINER_CONTENTS_EXCEED_SCAN_LIMIT")
    return None


def _iter_tar_members(path: Path) -> Iterator[tuple[str, bytes] | ContainerReadError]:
    """Yield bounded ``(name, data)`` members from a tar-family archive."""
    member_count = 0
    total_bytes = 0
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            data = source.read(MAX_CONTAINER_MEMBER_BYTES + 1)
            member_count += 1
            total_bytes += len(data)
            error = _check_member_limits(member_count, total_bytes, data)
            if error is not None:
                yield error
                return
            yield member.name, data


def _iter_zip_members(path: Path) -> Iterator[tuple[str, bytes] | ContainerReadError]:
    """Yield bounded ``(name, data)`` members from a zip-family/office-document archive."""
    member_count = 0
    total_bytes = 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            if member.file_size > MAX_CONTAINER_MEMBER_BYTES:
                yield ContainerReadError("CONTAINER_CONTENTS_EXCEED_SCAN_LIMIT")
                return
            data = archive.read(member)
            member_count += 1
            total_bytes += len(data)
            error = _check_member_limits(member_count, total_bytes, data)
            if error is not None:
                yield error
                return
            yield member.filename, data


def _iter_stream_member(path: Path, opener: Callable[[Path, str], Any]) -> Iterator[tuple[str, bytes] | ContainerReadError]:
    """Yield the single bounded member of a whole-file-compressed stream (gzip/bz2/xz)."""
    with opener(path, "rb") as source:
        data = source.read(MAX_CONTAINER_MEMBER_BYTES + 1)
    error = _check_member_limits(1, len(data), data)
    if error is not None:
        yield error
        return
    yield path.stem, data


def iter_container_members(path: Path) -> Iterator[tuple[str, bytes] | ContainerReadError]:
    """Iterate bounded container members without ever extracting the archive to disk.

    Yields ``(name, data)`` tuples for each member that fits within
    ``MAX_CONTAINER_MEMBERS``/``MAX_CONTAINER_MEMBER_BYTES``/``MAX_CONTAINER_TOTAL_BYTES``,
    or yields a single terminal ``ContainerReadError`` and stops (over-limit
    containers or extraction failures must not become silently clean).
    """
    name = path.name.lower()
    try:
        if name.endswith((".tar", ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz", ".tbz2", ".txz")):
            yield from _iter_tar_members(path)
        elif Path(name).suffix in ZIP_CONTAINER_SUFFIXES:
            yield from _iter_zip_members(path)
        elif Path(name).suffix in GZIP_CONTAINER_SUFFIXES:
            yield from _iter_stream_member(path, gzip.open)
        elif Path(name).suffix in BZIP2_CONTAINER_SUFFIXES:
            yield from _iter_stream_member(path, bz2.open)
        elif Path(name).suffix in XZ_CONTAINER_SUFFIXES:
            yield from _iter_stream_member(path, lzma.open)
        else:  # pragma: no cover - asset_kind keeps this branch unreachable.
            yield ContainerReadError("CONTAINER_CONTENTS_SCANNER_UNAVAILABLE")
    except (OSError, EOFError, gzip.BadGzipFile, lzma.LZMAError, tarfile.TarError, zipfile.BadZipFile):
        yield ContainerReadError("CONTAINER_CONTENTS_EXTRACTION_FAILED")
