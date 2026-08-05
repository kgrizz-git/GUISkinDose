"""Tests for value-safe HoundDog required/advisory behavior."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts import run_hounddog_advisory


def test_missing_hounddog_is_not_clean_when_receipt_requires_it(monkeypatch) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: None)

    assert run_hounddog_advisory.main(["--require-installed"]) == 2


def test_missing_hounddog_remains_nonblocking_for_manual_advisory(monkeypatch) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: None)

    assert run_hounddog_advisory.main([]) == 0


def test_missing_scan_root_keeps_required_mode_fail_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: "hounddog")

    assert run_hounddog_advisory.main(["--require-installed", "--scan-root", str(tmp_path / "missing")]) == 2


def test_completed_scan_with_findings_requires_triage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: "hounddog")

    def fake_run(command, **_kwargs):
        report_path = Path(command[command.index("--output-path") + 1])
        report_path.write_text(json.dumps({"dataflows": [{}]}), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_hounddog_advisory.subprocess, "run", fake_run)

    assert run_hounddog_advisory.main(["--scan-root", str(tmp_path)]) == 1


def test_nonzero_scanner_exit_is_not_clean_in_required_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: "hounddog")

    def fake_run(command, **_kwargs):
        report_path = Path(command[command.index("--output-path") + 1])
        report_path.write_text(json.dumps({"dataflows": []}), encoding="utf-8")
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr(run_hounddog_advisory.subprocess, "run", fake_run)

    assert run_hounddog_advisory.main(["--require-installed", "--scan-root", str(tmp_path)]) == 2
