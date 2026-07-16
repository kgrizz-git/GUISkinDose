"""Regression tests for privacy-safe diagnostics and opaque labels."""

from __future__ import annotations

import io
import logging

import pytest

from mypyskindose.privacy import (
    install_value_safe_excepthook,
    opaque_exam_label,
    safe_error_event,
    safe_user_error,
    safe_warning,
)


def _captured_logger(name: str) -> tuple[logging.Logger, logging.StreamHandler[io.StringIO], io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger(name)
    logger.addHandler(handler)
    return logger, handler, stream


def test_safe_error_event_suppresses_exception_message_and_path() -> None:
    sentinel = "PATIENT-SENTINEL-/Users/private/exam.dcm"
    logger, handler, stream = _captured_logger("mypyskindose.test.privacy")

    try:
        safe_error_event(logger, "dose_calculation", RuntimeError(sentinel))
    finally:
        logger.removeHandler(handler)

    output = stream.getvalue()
    assert sentinel not in output
    assert "RuntimeError" in output
    assert "dose_calculation" in output


def test_safe_warning_accepts_only_non_sensitive_scalars() -> None:
    logger, handler, stream = _captured_logger("mypyskindose.test.privacy.warning")
    try:
        safe_warning(logger, "beam_miss_summary", missed=2, total=4)
    finally:
        logger.removeHandler(handler)

    assert "missed=2" in stream.getvalue()
    with pytest.raises(TypeError):
        safe_warning(logger, "unsafe", source="patient-name.dcm")  # type: ignore[arg-type]


def test_opaque_exam_label_and_user_error_are_source_independent() -> None:
    assert opaque_exam_label(0) == "Exam 1"
    assert opaque_exam_label(4) == "Exam 5"
    assert safe_user_error("report_export") == "Operation failed (report_export)."
    with pytest.raises(ValueError):
        opaque_exam_label(-1)


def test_value_safe_excepthook_suppresses_traceback_and_exception_text(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    logger = logging.getLogger("mypyskindose.test.privacy.hook")
    original = __import__("sys").excepthook
    monkeypatch.setattr(__import__("sys"), "excepthook", original)
    install_value_safe_excepthook(logger, "cli_run")

    sentinel = "PATIENT-SENTINEL-/private/exam.dcm"
    exc = RuntimeError(sentinel)
    __import__("sys").excepthook(type(exc), exc, exc.__traceback__)

    captured = capsys.readouterr()
    assert sentinel not in captured.err
    assert "Operation failed (cli_run)." in captured.err
