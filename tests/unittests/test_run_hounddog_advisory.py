"""Tests for value-safe HoundDog required/advisory behavior."""

from __future__ import annotations

from scripts import run_hounddog_advisory


def test_missing_hounddog_is_not_clean_when_receipt_requires_it(monkeypatch) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: None)

    assert run_hounddog_advisory.main(["--require-installed"]) == 2


def test_missing_hounddog_remains_nonblocking_for_manual_advisory(monkeypatch) -> None:
    monkeypatch.setattr(run_hounddog_advisory.shutil, "which", lambda _name: None)

    assert run_hounddog_advisory.main([]) == 0
