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
        if not isinstance(cell, dict):
            continue
        mappings: list[object] = []
        attachments = cell.get("attachments", {})
        if isinstance(attachments, dict):
            mappings.extend(attachments.values())
        outputs = cell.get("outputs", [])
        if isinstance(outputs, list):
            mappings.extend(output.get("data", {}) for output in outputs if isinstance(output, dict))
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
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
                if len(images) >= MAX_RENDERED_IMAGES:
                    raise RuntimeError("notebook_image_count_exceeded")
                target = directory / f"notebook-{index}{suffix}"
                target.write_bytes(data)
                images.append(target)
                index += 1
    return images


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
        normalized = Path(relative.as_posix())
        source = (root / normalized).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            print("ERROR: image path escaped the private snapshot.", file=sys.stderr)
            return 2
        if not source.is_file():
            print(f"ERROR: image input unavailable path_token={path_token(normalized)}.", file=sys.stderr)
            return 2
        try:
            with tempfile.TemporaryDirectory(prefix="image-privacy-private-") as temp_dir:
                private = Path(temp_dir)
                images = extracted_images(source, private)
                texts: list[str] = []
                for index, image in enumerate(images):
                    converted = private / f"converted-{index}.png"
                    convert_to_png(image, converted)
                    texts.append(ocr_image(converted))
                deterministic = sum(len(text_findings(normalized.as_posix(), text)) for text in texts)
                nlp = presidio_count(engine, texts)
        except Exception as exc:
            print(
                f"ERROR: image privacy scan failed path_token={path_token(normalized)} "
                f"({type(exc).__name__}).",
                file=sys.stderr,
            )
            return 2
        findings = deterministic + nlp
        if findings:
            if is_hash_pinned_approved(root, normalized):
                reviewed_findings += findings
                print(
                    f"ADVISORY: image privacy finding(s) explicitly triaged by exact-hash inventory review "
                    f"path_token={path_token(normalized)}; OCR text and values suppressed."
                )
                continue
            total_findings += findings
            print(
                f"ADVISORY: image privacy scan found {findings} potential finding(s) "
                f"path_token={path_token(normalized)}; OCR text and values suppressed."
            )
    if total_findings:
        print(f"Image privacy advisory complete: {total_findings} finding(s); triage required.")
        return 1
    if reviewed_findings:
        print(
            f"Image privacy advisory complete: {reviewed_findings} finding(s) explicitly triaged "
            "by exact-hash human review."
        )
    else:
        print(f"Image privacy advisory clean: {len(args.paths)} asset(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
