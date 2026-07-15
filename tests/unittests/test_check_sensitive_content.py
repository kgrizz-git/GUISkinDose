"""Tests for the tracked-content and approved-asset admission gate."""

from __future__ import annotations

import json
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path

from reportlab.pdfgen import canvas

from scripts.check_commit_message import scan_commit_message
from scripts import check_sensitive_content
from scripts.check_sensitive_content import asset_kind, is_probably_binary, run_checks, sha256


def _write_policy(root: Path, assets: list[dict[str, object]]) -> None:
    docs = root / "dev-docs"
    docs.mkdir(exist_ok=True)
    (docs / "approved_asset_inventory.json").write_text(
        json.dumps({"version": 1, "assets": assets}), encoding="utf-8"
    )
    (docs / "sensitive_content_allowlist.json").write_text(
        json.dumps({"version": 1, "allowed_findings": []}), encoding="utf-8"
    )


def _asset_entry(root: Path, path: str, *, status: str = "approved") -> dict[str, object]:
    return {
        "path": path,
        "sha256": sha256(root / path),
        "kind": "image",
        "purpose": "Test fixture",
        "review": {"status": status, "reviewer": "tester", "reviewed_on": "2026-07-13"},
    }


def _dicom_asset_entry(root: Path, path: str) -> dict[str, object]:
    entry = _asset_entry(root, path)
    entry["kind"] = "dicom"
    entry["dicom_review"] = {
        "direct_identifiers_reviewed": True,
        "private_tags_reviewed": True,
        "burned_in_text_reviewed": True,
    }
    return entry


def _container_asset_entry(root: Path, path: str, *, kind: str = "office_document") -> dict[str, object]:
    entry = _asset_entry(root, path)
    entry["kind"] = kind
    entry["container_review"] = {
        "embedded_files_reviewed": True,
        "embedded_images_reviewed": True,
        "embedded_dicom_reviewed": True,
    }
    return entry


def test_approved_asset_passes(tmp_path: Path) -> None:
    asset = tmp_path / "diagram.png"
    asset.write_bytes(b"not a real image, but a hash-pinned asset")
    _write_policy(tmp_path, [_asset_entry(tmp_path, "diagram.png")])

    assert run_checks(tmp_path, paths=["diagram.png"]) == []


def test_missing_or_changed_asset_fails(tmp_path: Path) -> None:
    asset = tmp_path / "diagram.png"
    asset.write_bytes(b"first version")
    entry = _asset_entry(tmp_path, "diagram.png")
    _write_policy(tmp_path, [entry])
    asset.write_bytes(b"changed version")
    (tmp_path / "new.dcm").write_bytes(b"new opaque input")

    findings = run_checks(tmp_path, paths=["diagram.png", "new.dcm"])
    assert {(finding.path, finding.rule) for finding in findings} == {
        ("diagram.png", "ASSET_HASH_NOT_APPROVED"),
        ("new.dcm", "ASSET_NOT_IN_APPROVED_INVENTORY"),
    }


def test_pending_baseline_becomes_error_in_strict_mode(tmp_path: Path) -> None:
    asset = tmp_path / "diagram.png"
    asset.write_bytes(b"baseline")
    _write_policy(tmp_path, [_asset_entry(tmp_path, "diagram.png", status="pending")])

    advisory = run_checks(tmp_path, paths=["diagram.png"])
    strict = run_checks(tmp_path, paths=["diagram.png"], require_approved_assets=True)
    assert [(finding.rule, finding.level) for finding in advisory] == [("ASSET_MANUAL_REVIEW_PENDING", "warning")]
    assert [(finding.rule, finding.level) for finding in strict] == [("ASSET_MANUAL_REVIEW_PENDING", "error")]


def test_sensitive_text_is_reported_without_echoing_value(tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    text.write_text("contact=" + "person" + "@hospital.test\n", encoding="utf-8")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["notes.txt"])
    assert [(finding.path, finding.rule, finding.location) for finding in findings] == [
        ("notes.txt", "EMAIL_ADDRESS", "1")
    ]
    assert "person" not in findings[0].render()


def test_extensionless_file_requires_an_inventory_entry(tmp_path: Path) -> None:
    extensionless = tmp_path / "possible_dicom"
    extensionless.write_bytes(b"opaque input")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["possible_dicom"])
    assert [(finding.path, finding.rule) for finding in findings] == [
        ("possible_dicom", "ASSET_NOT_IN_APPROVED_INVENTORY")
    ]


def test_extensionless_dicom_preamble_requires_dicom_review(tmp_path: Path) -> None:
    possible_dicom = tmp_path / "possible_dicom"
    possible_dicom.write_bytes(b"\0" * 128 + b"DICM" + b"synthetic payload")
    incomplete_entry = _asset_entry(tmp_path, "possible_dicom")
    incomplete_entry["kind"] = "dicom"
    _write_policy(tmp_path, [incomplete_entry])

    incomplete_findings = run_checks(tmp_path, paths=["possible_dicom"])
    assert any(finding.rule == "DICOM_REVIEW_FIELDS_INCOMPLETE" for finding in incomplete_findings)

    _write_policy(tmp_path, [_dicom_asset_entry(tmp_path, "possible_dicom")])

    assert asset_kind("possible_dicom", possible_dicom) == "dicom"
    assert not any(finding.level == "error" for finding in run_checks(tmp_path, paths=["possible_dicom"]))


def test_diagnostic_artifact_and_internal_endpoint_are_blocked_without_echoing_value(tmp_path: Path) -> None:
    artifact = tmp_path / "session.log"
    artifact.write_text("endpoint=" + "192.168." + "9.2\n", encoding="utf-8")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["session.log"])
    assert {(finding.rule, finding.level) for finding in findings} == {
        ("DIAGNOSTIC_ARTIFACT_FORBIDDEN", "error"),
        ("PRIVATE_IPV4_ADDRESS", "error"),
    }
    assert "192.168" not in "\n".join(finding.render() for finding in findings)


def test_contextual_patient_identifier_is_blocked_but_test_placeholder_is_allowed(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.txt"
    metadata.write_text("patient" + "_id=AB-" + "42\npatient_id=TEST\n", encoding="utf-8")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["metadata.txt"])
    assert [(finding.rule, finding.location) for finding in findings] == [
        ("CONTEXTUAL_PATIENT_IDENTIFIER", "1")
    ]


def test_notebook_embedded_visual_requires_an_inventory_entry(tmp_path: Path) -> None:
    notebook = tmp_path / "rendered.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "outputs": [{"data": {"image/png": "synthetic"}}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_policy(tmp_path, [])

    assert asset_kind("rendered.ipynb", notebook) == "notebook_embedded_visual"
    assert [(finding.path, finding.rule) for finding in run_checks(tmp_path, paths=["rendered.ipynb"])] == [
        ("rendered.ipynb", "ASSET_NOT_IN_APPROVED_INVENTORY")
    ]


def test_tex_source_is_scanned_as_plain_text(tmp_path: Path) -> None:
    tex_source = tmp_path / "report.tex"
    tex_source.write_text("\\author{person" + "@hospital.test}\n", encoding="utf-8")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["report.tex"])

    assert [(finding.rule, finding.location) for finding in findings] == [("EMAIL_ADDRESS", "1")]


def test_postscript_requires_inventory_and_scans_strings(tmp_path: Path) -> None:
    postscript = tmp_path / "report.ps"
    postscript.write_bytes(b"%!PS\n(patient" + b"_id=AB-42) show\n")
    _write_policy(tmp_path, [])

    findings = run_checks(tmp_path, paths=["report.ps"])

    assert {(finding.rule, finding.level) for finding in findings} == {
        ("ASSET_NOT_IN_APPROVED_INVENTORY", "error"),
        ("CONTEXTUAL_PATIENT_IDENTIFIER", "error"),
    }
    assert asset_kind("report.ps", postscript) == "postscript"


def test_pdf_requires_inventory_and_scans_metadata_and_page_text(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"synthetic PDF fixture")
    _write_policy(tmp_path, [])

    class FakePage:
        def extract_text(self) -> str:
            return "patient" + "_id=AB-42"

    class FakePdfReader:
        def __init__(self, path: Path) -> None:
            self.is_encrypted = False
            self.metadata = {"/Author": "person" + "@hospital.test"}
            self.pages = [FakePage()]
            self.attachments: dict[str, list[bytes]] = {}

    monkeypatch.setattr(check_sensitive_content, "PdfReader", FakePdfReader)
    findings = run_checks(tmp_path, paths=["report.pdf"])

    assert {(finding.rule, finding.location) for finding in findings} == {
        ("ASSET_NOT_IN_APPROVED_INVENTORY", ""),
        ("CONTEXTUAL_PATIENT_IDENTIFIER", "page1:1"),
        ("EMAIL_ADDRESS", "metadata:1"),
    }
    assert asset_kind("report.pdf", pdf) == "pdf"


def test_real_pdf_page_text_is_scanned(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    document = canvas.Canvas(str(pdf))
    document.drawString(72, 720, "patient" + "_id=AB-42")
    document.save()
    entry = _asset_entry(tmp_path, "report.pdf")
    entry["kind"] = "pdf"
    _write_policy(tmp_path, [entry])

    findings = run_checks(tmp_path, paths=["report.pdf"])

    assert [(finding.rule, finding.location) for finding in findings] == [
        ("CONTEXTUAL_PATIENT_IDENTIFIER", "page1:1")
    ]


def test_inventory_kind_must_match_detected_asset_type(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"synthetic PDF fixture")
    _write_policy(tmp_path, [_asset_entry(tmp_path, "report.pdf")])

    findings = run_checks(tmp_path, paths=["report.pdf"])

    assert {(finding.rule, finding.level) for finding in findings} == {
        ("ASSET_INVENTORY_KIND_MISMATCH", "error"),
        ("PDF_TEXT_EXTRACTION_FAILED", "error"),
    }


def test_office_container_scans_text_and_requires_embedded_content_review(tmp_path: Path) -> None:
    document = tmp_path / "report.docx"
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/document.xml", "patient" + "_id=AB-42")
        archive.writestr("word/media/image1.png", b"synthetic image")
        archive.writestr("word/embeddings/input", b"\0" * 128 + b"DICM")
    entry = _container_asset_entry(tmp_path, "report.docx")
    entry.pop("container_review")
    _write_policy(tmp_path, [entry])

    findings = run_checks(tmp_path, paths=["report.docx"])

    assert {(finding.rule, finding.level, finding.location) for finding in findings} == {
        ("CONTAINER_DICOM_MEMBER_PRESENT", "warning", ""),
        ("CONTAINER_REVIEW_FIELDS_INCOMPLETE", "error", ""),
        ("CONTEXTUAL_PATIENT_IDENTIFIER", "error", "member1:1"),
    }
    assert asset_kind("report.docx", document) == "office_document"


def test_tar_archive_scans_text_and_preserves_cleared_container_behavior(tmp_path: Path) -> None:
    archive_path = tmp_path / "fixture.tar.gz"
    payload = b"patient" + b"_id=AB-42\n"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("events.txt")
        member.size = len(payload)
        archive.addfile(member, BytesIO(payload))
    _write_policy(tmp_path, [_container_asset_entry(tmp_path, "fixture.tar.gz", kind="archive")])

    findings = run_checks(tmp_path, paths=["fixture.tar.gz"])

    assert [(finding.rule, finding.location) for finding in findings] == [
        ("CONTEXTUAL_PATIENT_IDENTIFIER", "member1:1")
    ]
    assert asset_kind("fixture.tar.gz", archive_path) == "archive"


def test_commit_message_is_scanned_without_allowlist_or_value_echo(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Investigate PACS at " + "pacs" + "://scanner.internal/study\n", encoding="utf-8")

    findings = scan_commit_message(message)
    assert [(finding.path, finding.rule, finding.location) for finding in findings] == [
        ("COMMIT_MESSAGE", "DICOM_PACS_URI", "1")
    ]
    assert "scanner.internal" not in findings[0].render()


def test_utf8_character_split_at_binary_sample_boundary_is_not_binary(tmp_path: Path) -> None:
    markdown = tmp_path / "notes.md"
    markdown.write_bytes(b"a" * 8191 + "—".encode("utf-8"))

    assert is_probably_binary(markdown) is False
