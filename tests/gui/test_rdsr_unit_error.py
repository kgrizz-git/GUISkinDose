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
            "This RDSR reports reference point dose in 'mGy', but GUISkinDose expects 'Gy'."
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


def test_load_rdsr_surfaces_input_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose.rdsr_input_checks import RdsrInputError

    def _raise(*_args, **_kwargs):
        raise RdsrInputError("This file contains no X-ray irradiation events, so there is nothing to calculate.")

    monkeypatch.setattr(exam_loaders, "rdsr_normalizer", _raise)

    ok, message = exam_loaders.load_rdsr(_EXAMPLE_RDSR, AppState())

    assert ok is False
    assert "no X-ray irradiation events" in message


def test_load_tabular_schema_detection_names_marker_and_two_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose.input_adapters.registry import SchemaDetectionError

    def _raise(*_args, **_kwargs):
        raise SchemaDetectionError("Schema auto-detection: headers overlapped known schemas.")

    monkeypatch.setattr(exam_loaders, "_parse_tabular", _raise)
    state = AppState()

    ok, message = exam_loaders.load_tabular(Path("events.csv"), state)

    assert ok is False
    assert state.import_has_errors is True
    assert "one source's own column" in message
    assert "at least two columns it recognizes" in message
    assert "two sources both fit" in message
    assert "headers overlapped" not in message


def test_load_tabular_surfaces_input_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose.rdsr_input_checks import RdsrInputError

    def _raise(*_args, **_kwargs):
        raise RdsrInputError("This RDSR lacks data GUISkinDose needs: tube voltage (kVp) (missing in 1 of 3 events).")

    monkeypatch.setattr(exam_loaders, "_parse_tabular", _raise)
    state = AppState()

    ok, message = exam_loaders.load_tabular(Path("events.csv"), state)

    assert ok is False
    assert "tube voltage (kVp)" in message
    assert state.import_has_errors is True


def test_rejected_rdsr_leaves_offsets_and_raw_preview_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected file must not zero the previous exams' offsets or replace the raw preview."""
    import pandas as pd

    from guiskindose.rdsr_input_checks import RdsrInputError

    def _raise(*_args, **_kwargs):
        raise RdsrInputError("This RDSR lacks data GUISkinDose needs.")

    monkeypatch.setattr(exam_loaders, "rdsr_normalizer", _raise)
    state = AppState()
    state.d_lon, state.d_ver, state.d_lat = 5.0, -2.0, 1.5
    state.swap_lat_lon = True
    previous_raw = pd.DataFrame({"marker": [1]})
    state.rdsr_raw_df = previous_raw

    ok, _message = exam_loaders.load_rdsr(_EXAMPLE_RDSR, state)

    assert ok is False
    assert (state.d_lon, state.d_ver, state.d_lat) == (5.0, -2.0, 1.5)
    assert state.swap_lat_lon is True
    assert state.rdsr_raw_df is previous_raw
