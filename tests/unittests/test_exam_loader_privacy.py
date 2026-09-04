"""Regression tests for value-safe GUI load diagnostics."""

from __future__ import annotations

import logging

import pytest

# exam_loaders transitively imports NiceGUI via page_context; skip in core CI.
pytest.importorskip("nicegui")

from guiskindose.gui.exam_loaders import _record_load_failure


def test_load_failure_log_suppresses_exception_message() -> None:
    sensitive_message = "could not open " + "/Users/" + "patient_name/RDSR.dcm"
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose.gui.exam_loaders")
    handler = _Capture(level=logging.ERROR)
    logger.addHandler(handler)
    try:
        _record_load_failure("DICOM_RDSR_LOAD", ValueError(sensitive_message))
    finally:
        logger.removeHandler(handler)

    text = "\n".join(messages)
    # Trailing paren dropped so the assertion tolerates the value-free
    # " at <path>:<lineno> in <func>" location suffix safe_error_event may add.
    assert "DICOM_RDSR_LOAD failed (error_type=ValueError" in text
    assert "patient_name" not in text
