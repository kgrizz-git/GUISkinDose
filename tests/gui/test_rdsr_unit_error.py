"""RDSR unit-mismatch is surfaced to the GUI with a clear, unit-naming message.

When ``rdsr_normalizer`` raises ``RdsrUnitError``, ``load_rdsr`` must return that
specific message rather than the generic "Could not read this DICOM RDSR file".
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui import exam_loaders
from guiskindose.gui.state import AppState
from guiskindose.rdsr_normalizer import RdsrUnitError

_EXAMPLE_RDSR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)


def test_load_rdsr_surfaces_unit_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args, **_kwargs):
        raise RdsrUnitError(
            "This RDSR reports reference point dose in 'mGy', but MyPySkinDose expects 'Gy'."
        )

    monkeypatch.setattr(exam_loaders, "rdsr_normalizer", _raise)

    ok, message = exam_loaders.load_rdsr(_EXAMPLE_RDSR, AppState())

    assert ok is False
    assert "reference point dose" in message
    assert "mGy" in message
    assert "Could not read this DICOM RDSR file" not in message


def test_generic_rdsr_failure_keeps_generic_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args, **_kwargs):
        raise ValueError("some other parse problem")

    monkeypatch.setattr(exam_loaders, "rdsr_normalizer", _raise)

    ok, message = exam_loaders.load_rdsr(_EXAMPLE_RDSR, AppState())

    assert ok is False
    assert message == "Could not read this DICOM RDSR file. Check the file and try again."
