"""Privacy-safe diagnostics and opaque runtime labels.

Only stable, source-controlled operation codes and non-sensitive scalar metrics
belong in application logs.  Clinical values, paths, filenames, identifiers,
and exception messages must stay out of every diagnostic sink.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Final


_CODE_RE: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SAFE_EXCEPTION_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")


def _code(value: str, *, label: str) -> str:
    if not _CODE_RE.fullmatch(value):
        raise ValueError(f"{label} must be a stable diagnostic code")
    return value


def exception_class_name(exc: BaseException) -> str:
    """Return a value-safe exception class name without its message."""
    name = type(exc).__name__
    return name if _SAFE_EXCEPTION_RE.fullmatch(name) else "Exception"


def safe_error_event(
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
    *,
    level: int = logging.ERROR,
) -> None:
    """Log an operation code and exception class, never exception text."""
    logger.log(
        level,
        "%s failed (error_type=%s)",
        _code(operation, label="operation"),
        exception_class_name(exc),
    )


def safe_warning(logger: logging.Logger, code: str, **metrics: int | float | bool | None) -> None:
    """Log a warning code with allowlisted scalar metrics only.

    String metrics are deliberately not accepted: even apparently harmless
    strings tend to become filenames, identifiers, or raw vendor values later.
    """
    warning_code = _code(code, label="warning code")
    rendered: list[str] = []
    for key in sorted(metrics):
        metric_key = _code(key, label="metric name")
        value = metrics[key]
        if value is not None and not isinstance(value, (bool, int, float)):
            raise TypeError("diagnostic metrics must be bool, int, float, or None")
        rendered.append(f"{metric_key}={value}")
    suffix = f" ({', '.join(rendered)})" if rendered else ""
    logger.warning("%s%s", warning_code, suffix)


def opaque_exam_label(index: int) -> str:
    """Return a one-based label that cannot contain source or DICOM text."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("exam index must be a non-negative integer")
    return f"Exam {index + 1}"


def safe_user_error(operation: str) -> str:
    """Return a generic user-facing error carrying only a stable code."""
    return f"Operation failed ({_code(operation, label='operation')})."


def install_value_safe_excepthook(logger: logging.Logger, operation: str = "cli_run") -> None:
    """Suppress raw uncaught tracebacks at a clinical-data CLI boundary."""
    operation_code = _code(operation, label="operation")

    def _hook(exc_type: type[BaseException], exc: BaseException, traceback: object) -> None:
        del traceback
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, None)
            return
        safe_error_event(logger, operation_code, exc)
        print(safe_user_error(operation_code), file=sys.stderr)

    sys.excepthook = _hook
