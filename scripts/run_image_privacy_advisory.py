#!/usr/bin/env python3
"""OCR changed rendered assets locally and scan extracted text without emitting values."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

try:
    from approved_asset_review import is_hash_pinned_approved
    from check_sensitive_content import text_findings
    from run_presidio_advisory import PII_ENTITIES, make_engine
except ModuleNotFoundError:  # Imported as scripts.run_image_privacy_advisory in tests.
    from scripts.approved_asset_review import is_hash_pinned_approved
    from scripts.check_sensitive_content import text_findings
    from scripts.run_presidio_advisory import PII_ENTITIES, make_engine

IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
OFFICE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
MAX_OCR_TEXT_BYTES = 2 * 1024 * 1024
MAX_EMBEDDED_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RENDERED_IMAGES = 100


def path_token(path: Path) -> str:
    return hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:12]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Snapshot-relative rendered asset paths.")
    parser.add_argument("--scan-root", type=Path, required=True, help="Private materialized snapshot root.")
    return parser.parse_args(argv)


def convert_to_png(source: Path, destination: Path) -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow is a core dependency
        raise RuntimeError("pillow_missing") from exc
    with Image.open(source) as image:
        image.seek(0)
        if image.mode not in {"1", "L", "RGB", "RGBA"}:
            image = image.convert("RGB")
        image.save(destination, format="PNG")


def ocr_image(image_path: Path) -> str:
    binary = shutil.which("tesseract")
    if binary is None:
        raise RuntimeError("tesseract_missing")
    completed = subprocess.run(
        [binary, str(image_path), "stdout", "--psm", "6"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("tesseract_failed")
    if len(completed.stdout) > MAX_OCR_TEXT_BYTES:
        raise RuntimeError("ocr_text_too_large")
    return completed.stdout.decode("utf-8", "replace")


def render_pdf(source: Path, directory: Path) -> list[Path]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - pypdf is a core dependency
        raise RuntimeError("pypdf_missing") from exc
    try:
        if len(PdfReader(source).pages) > MAX_RENDERED_IMAGES:
            raise RuntimeError("pdf_page_limit_exceeded")
    except OSError as exc:
        raise RuntimeError("pdf_read_failed") from exc
    binary = shutil.which("pdftoppm")
    if binary is None:
        raise RuntimeError("pdftoppm_missing")
    prefix = directory / "page"
    completed = subprocess.run(
        [binary, "-png", "-r", "150", str(source), str(prefix)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("pdf_render_failed")
    return sorted(directory.glob("page-*.png"))


def office_images(source: Path, directory: Path) -> list[Path]:
    images: list[Path] = []
    total_bytes = 0
    try:
        with zipfile.ZipFile(source) as archive:
            for index, info in enumerate(archive.infolist()):
                member = Path(info.filename)
                if member.suffix.lower() not in IMAGE_SUFFIXES or "/media/" not in f"/{info.filename}":
                    continue
                if info.file_size > MAX_EMBEDDED_IMAGE_BYTES:
                    raise RuntimeError("embedded_image_too_large")
                total_bytes += info.file_size
                if len(images) >= MAX_RENDERED_IMAGES or total_bytes > MAX_EMBEDDED_IMAGE_BYTES:
                    raise RuntimeError("embedded_image_collection_too_large")
                target = directory / f"office-{index}{member.suffix.lower()}"
                target.write_bytes(archive.read(info))
                images.append(target)
    except zipfile.BadZipFile as exc:
        raise RuntimeError("office_container_invalid") from exc
    return images


def notebook_images(source: Path, directory: Path) -> list[Path]:
    try:
        notebook = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("notebook_invalid") from exc
    images: list[Path] = []
    index = 0
    for cell in notebook.get("cells", []) if isinstance(notebook, dict) else []:
        for mapping in _notebook_cell_mappings(cell):
            for suffix, data in _notebook_image_data(mapping):
                index = _append_notebook_image(images, directory, index, suffix, data)
    return images


def _notebook_cell_mappings(cell: object) -> list[object]:
    """Return attachment and output-data mappings from one notebook cell."""
    if not isinstance(cell, dict):
        return []
    mappings: list[object] = []
    attachments = cell.get("attachments", {})
    if isinstance(attachments, dict):
        mappings.extend(attachments.values())
    outputs = cell.get("outputs", [])
    if isinstance(outputs, list):
        mappings.extend(output.get("data", {}) for output in outputs if isinstance(output, dict))
    return mappings


def _notebook_image_data(mapping: object) -> Iterable[tuple[str, bytes]]:
    """Yield validated PNG/JPEG notebook payloads without retaining text outputs."""
    if not isinstance(mapping, dict):
        return
    for mime, encoded in mapping.items():
        suffix = {"image/png": ".png", "image/jpeg": ".jpg"}.get(str(mime))
        if suffix is None or not isinstance(encoded, str):
            continue
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise RuntimeError("notebook_image_invalid") from exc
        if len(data) > MAX_EMBEDDED_IMAGE_BYTES:
            raise RuntimeError("notebook_image_too_large")
        yield suffix, data


def _append_notebook_image(
    images: list[Path], directory: Path, index: int, suffix: str, data: bytes
) -> int:
    """Write one bounded extracted image and return the next output index."""
    if len(images) >= MAX_RENDERED_IMAGES:
        raise RuntimeError("notebook_image_count_exceeded")
    target = directory / f"notebook-{index}{suffix}"
    target.write_bytes(data)
    images.append(target)
    return index + 1


def extracted_images(source: Path, directory: Path) -> list[Path]:
    suffix = source.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return [source]
    if suffix == ".pdf":
        return render_pdf(source, directory)
    if suffix in OFFICE_SUFFIXES:
        return office_images(source, directory)
    if suffix == ".ipynb":
        return notebook_images(source, directory)
    raise RuntimeError("unsupported_rendered_asset")


def presidio_count(engine: Any, texts: Iterable[str]) -> int:
    count = 0
    for text in texts:
        count += len(
            engine.analyze(
                text=text,
                language="en",
                entities=[*PII_ENTITIES, "PERSON"],
                score_threshold=0.85,
            )
        )
    return count


class ImageScanError(RuntimeError):
    """A value-safe image-scanner failure suitable for user-visible reporting."""


def _scan_image_asset(engine: Any, root: Path, relative: Path) -> tuple[Path, int]:
    """Scan one confined rendered asset and return its normalized path and finding count."""
    normalized = Path(relative.as_posix())
    source = (root / normalized).resolve()
    if not source.is_relative_to(root):
        raise ImageScanError("ERROR: image path escaped the private snapshot.")
    if not source.is_file():
        raise ImageScanError(f"ERROR: image input unavailable path_token={path_token(normalized)}.")
    try:
        with tempfile.TemporaryDirectory(prefix="image-privacy-private-") as temp_dir:
            private = Path(temp_dir)
            images = extracted_images(source, private)
            texts = _ocr_images(images, private)
            deterministic = sum(len(text_findings(normalized.as_posix(), text)) for text in texts)
            return normalized, deterministic + presidio_count(engine, texts)
    except Exception as exc:
        raise ImageScanError(
            f"ERROR: image privacy scan failed path_token={path_token(normalized)} ({type(exc).__name__})."
        ) from exc


def _ocr_images(images: Iterable[Path], directory: Path) -> list[str]:
    """Convert extracted assets to PNG and return only transient OCR text."""
    texts: list[str] = []
    for index, image in enumerate(images):
        converted = directory / f"converted-{index}.png"
        convert_to_png(image, converted)
        texts.append(ocr_image(converted))
    return texts


def _report_image_findings(root: Path, normalized: Path, findings: int) -> tuple[int, int]:
    """Print an advisory and split a finding count into unreviewed and reviewed totals."""
    if not findings:
        return 0, 0
    if is_hash_pinned_approved(root, normalized):
        print(
            f"ADVISORY: image privacy finding(s) explicitly triaged by exact-hash inventory review "
            f"path_token={path_token(normalized)}; OCR text and values suppressed."
        )
        return 0, findings
    print(
        f"ADVISORY: image privacy scan found {findings} potential finding(s) "
        f"path_token={path_token(normalized)}; OCR text and values suppressed."
    )
    return findings, 0


def _print_summary(paths: Sequence[Path], total_findings: int, reviewed_findings: int) -> int:
    """Print the value-safe image summary and return its advisory exit status."""
    if total_findings:
        print(f"Image privacy advisory complete: {total_findings} finding(s); triage required.")
        return 1
    if reviewed_findings:
        print(
            f"Image privacy advisory complete: {reviewed_findings} finding(s) explicitly triaged "
            "by exact-hash human review."
        )
    else:
        print(f"Image privacy advisory clean: {len(paths)} asset(s).")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.scan_root.resolve()
    if not root.is_dir():
        print("ERROR: image privacy scan did not run (scan_root_unavailable).", file=sys.stderr)
        return 2
    try:
        engine = make_engine()
    except Exception as exc:
        print(f"ERROR: image privacy scan did not start ({type(exc).__name__}).", file=sys.stderr)
        return 2

    total_findings = 0
    reviewed_findings = 0
    for relative in args.paths:
        try:
            normalized, findings = _scan_image_asset(engine, root, relative)
        except ImageScanError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        unreviewed, reviewed = _report_image_findings(root, normalized, findings)
        total_findings += unreviewed
        reviewed_findings += reviewed
    return _print_summary(args.paths, total_findings, reviewed_findings)


if __name__ == "__main__":
    raise SystemExit(main())
