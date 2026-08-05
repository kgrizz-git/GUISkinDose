"""Tests for bounded extraction in the local image privacy adapter."""

from __future__ import annotations

import base64
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfWriter

from scripts import run_image_privacy_advisory as image_advisory
from scripts.run_image_privacy_advisory import notebook_images, office_images, render_pdf


def test_office_extraction_only_reads_media_images(tmp_path: Path) -> None:
    source = tmp_path / "fixture.docx"
    output = tmp_path / "output"
    output.mkdir()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/media/image1.png", b"synthetic-image")
        archive.writestr("word/document.xml", b"<document/>")

    images = office_images(source, output)

    assert len(images) == 1
    assert images[0].read_bytes() == b"synthetic-image"


def test_notebook_extraction_handles_embedded_png_without_retaining_text(tmp_path: Path) -> None:
    source = tmp_path / "fixture.ipynb"
    output = tmp_path / "output"
    output.mkdir()
    image_bytes = b"synthetic-png"
    source.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "outputs": [{"data": {"image/png": base64.b64encode(image_bytes).decode("ascii")}}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    images = notebook_images(source, output)

    assert len(images) == 1
    assert images[0].read_bytes() == image_bytes


def test_unreviewed_image_findings_remain_actionable(tmp_path: Path, monkeypatch) -> None:
    """The reporting helper must retain findings that lack exact-hash approval."""
    monkeypatch.setattr(image_advisory, "is_hash_pinned_approved", lambda *_args, **_kwargs: False)

    assert image_advisory._report_image_findings(tmp_path, Path("fixture.png"), 2) == (2, 0)


def test_image_scan_helpers_cover_success_error_and_reviewed_paths(tmp_path: Path, monkeypatch) -> None:
    """The scanner keeps extracted OCR text transient while classifying all receipt outcomes."""
    root = tmp_path / "snapshot"
    root.mkdir()
    source = root / "fixture.png"
    source.write_bytes(b"synthetic")

    def fake_convert(_source: Path, destination: Path) -> None:
        destination.write_bytes(b"png")

    monkeypatch.setattr(image_advisory, "extracted_images", lambda path, _directory: [path])
    monkeypatch.setattr(image_advisory, "convert_to_png", fake_convert)
    monkeypatch.setattr(image_advisory, "ocr_image", lambda _path: "synthetic text")
    monkeypatch.setattr(image_advisory, "text_findings", lambda *_args: [object()])
    monkeypatch.setattr(image_advisory, "presidio_count", lambda *_args: 2)
    monkeypatch.setattr(image_advisory, "is_hash_pinned_approved", lambda *_args: True)

    normalized, findings = image_advisory._scan_image_asset(object(), root, Path("fixture.png"))

    assert (normalized, findings) == (Path("fixture.png"), 3)
    assert image_advisory._report_image_findings(root, normalized, findings) == (0, 3)
    assert image_advisory._report_image_findings(root, normalized, 0) == (0, 0)
    assert image_advisory._print_summary([normalized], 0, 3) == 0
    assert image_advisory._print_summary([normalized], 1, 0) == 1
    assert image_advisory._print_summary([normalized], 0, 0) == 0

    monkeypatch.setattr(image_advisory, "extracted_images", lambda *_args: (_ for _ in ()).throw(RuntimeError("bad")))
    with pytest.raises(image_advisory.ImageScanError, match="image privacy scan failed"):
        image_advisory._scan_image_asset(object(), root, Path("fixture.png"))


def test_image_main_accumulates_scanned_results(tmp_path: Path, monkeypatch) -> None:
    """The CLI reports an actionable exit status when its helper returns findings."""
    root = tmp_path / "snapshot"
    root.mkdir()
    source = root / "fixture.png"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(image_advisory, "make_engine", lambda: object())
    monkeypatch.setattr(image_advisory, "_scan_image_asset", lambda *_args: (Path("fixture.png"), 2))
    monkeypatch.setattr(image_advisory, "is_hash_pinned_approved", lambda *_args: False)

    assert image_advisory.main([str(source.relative_to(root)), "--scan-root", str(root)]) == 1


@pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="Poppler is an optional local OCR prerequisite")
def test_pdf_pages_render_locally_for_ocr(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    output = tmp_path / "output"
    output.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source.open("wb") as stream:
        writer.write(stream)

    pages = render_pdf(source, output)

    assert len(pages) == 1
    assert pages[0].suffix == ".png"
