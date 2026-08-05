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
