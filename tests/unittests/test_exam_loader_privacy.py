"""Regression tests for value-safe GUI load diagnostics."""

from __future__ import annotations

import logging

import pytest

# exam_loaders transitively imports NiceGUI via page_context; skip in core CI.
pytest.importorskip("nicegui")

from mypyskindose.gui.exam_loaders import _record_load_failure


def test_load_failure_log_suppresses_exception_message() -> None:
    sensitive_message = "could not open " + "/Users/" + "patient_name/RDSR.dcm"
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("mypyskindose.gui.exam_loaders")
    handler = _Capture(level=logging.ERROR)
    logger.addHandler(handler)
    try:
        _record_load_failure("DICOM_RDSR_LOAD", ValueError(sensitive_message))
    finally:
        logger.removeHandler(handler)

    text = "\n".join(messages)
    assert "DICOM_RDSR_LOAD failed (error_type=ValueError)" in text
    assert "patient_name" not in text
