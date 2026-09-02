"""Privacy-safe diagnostics and opaque runtime labels.

Only stable, source-controlled operation codes and non-sensitive scalar metrics
belong in application logs.  Clinical values, paths, filenames, identifiers,
and exception messages must stay out of every diagnostic sink.
"""

from __future__ import annotations

import logging
import re
import sys
import traceback
from pathlib import Path
from typing import Final

_CODE_RE: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
_SAFE_EXCEPTION_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
# Frame function names are code identifiers (incl. <module>, <lambda>, <listcomp>).
_SAFE_FRAME_NAME_RE: Final = re.compile(r"^[<A-Za-z_][A-Za-z0-9_>.]{0,79}$")
# Deepest frames are the most diagnostic; cap to keep log lines bounded.
_MAX_TRACEBACK_FRAMES: Final = 8


def _code(value: str, *, label: str) -> str:
    if not _CODE_RE.fullmatch(value):
        raise ValueError(f"{label} must be a stable diagnostic code")
    return value


def exception_class_name(exc: BaseException) -> str:
    """Return a value-safe exception class name without its message."""
    name = type(exc).__name__
    return name if _SAFE_EXCEPTION_RE.fullmatch(name) else "Exception"


def _relative_frame_path(filename: str) -> str:
    """Reduce a traceback frame's source path to a value-safe relative fragment.

    Traceback frames are always Python source files (never patient data), but
    their absolute paths can embed a home-directory/username, so strip to a
    package-relative fragment: from ``mypyskindose/`` for our own code, from
    inside ``site-packages/`` for dependencies, else the bare file name. Never
    returns an absolute path.
    """
    parts = Path(filename).parts
    if "mypyskindose" in parts:
        return Path(*parts[parts.index("mypyskindose") :]).as_posix()
    if "site-packages" in parts:
        return Path(*parts[parts.index("site-packages") + 1 :]).as_posix()
    return Path(filename).name


def _safe_frame(frame: traceback.FrameSummary) -> str:
    """Render one frame as ``path:lineno in func`` — no source text or locals."""
    name = frame.name if _SAFE_FRAME_NAME_RE.fullmatch(frame.name or "") else "?"
    return f"{_relative_frame_path(frame.filename)}:{frame.lineno} in {name}"


def innermost_location(exc: BaseException) -> str:
    """Return ``path:lineno in func`` for where ``exc`` was raised (or "").

    Value-free: only the code location, never the exception message or locals.
    Empty when the exception carries no traceback (e.g. constructed but never
    raised).
    """
    frames = traceback.extract_tb(exc.__traceback__)
    return _safe_frame(frames[-1]) if frames else ""


def safe_traceback(exc: BaseException) -> str:
    """Return a value-free traceback for ``exc`` and its cause/context chain.

    Includes only exception class names and ``path:lineno in func`` frame
    locations (deepest ``_MAX_TRACEBACK_FRAMES`` per exception). Never includes
    exception messages, source-line text, local values, or absolute paths, so it
    is safe to emit at DEBUG alongside the value-free one-line summary.
    """
    lines: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        prefix = "" if not lines else "caused by: "
        lines.append(f"{prefix}{exception_class_name(current)}")
        frames = traceback.extract_tb(current.__traceback__)[-_MAX_TRACEBACK_FRAMES:]
        lines.extend(f"  {_safe_frame(frame)}" for frame in frames)
        # Mirror CPython's traceback display: prefer an explicit cause; otherwise
        # follow the implicit context only when it was not suppressed (``from None``).
        if current.__cause__ is not None:
            current = current.__cause__
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return "\n".join(lines)


def safe_error_event(
    logger: logging.Logger,
    operation: str,
    exc: BaseException,
    *,
    level: int = logging.ERROR,
) -> None:
    """Log an operation code and exception class, never exception text.

    The one-line summary also carries the value-free code location where the
    exception was raised (``path:lineno in func``) when available. When DEBUG is
    enabled for ``logger``, a value-free traceback of the exception (and its
    cause/context chain) is emitted too — still message-, value-, and
    absolute-path-free — to make otherwise opaque errors (e.g. a bare
    ``RuntimeError``) diagnosable without exposing clinical data.
    """
    op = _code(operation, label="operation")
    error_type = exception_class_name(exc)
    location = innermost_location(exc)
    if location:
        logger.log(level, "%s failed (error_type=%s at %s)", op, error_type, location)
    else:
        logger.log(level, "%s failed (error_type=%s)", op, error_type)
    if logger.isEnabledFor(logging.DEBUG):
        detail = safe_traceback(exc)
        logger.debug("%s traceback (value-free):\n%s", op, detail)


def safe_warning(logger: logging.Logger, code: str, **metrics: float | bool | None) -> None:
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


def opaque_exam_index(label: str) -> int:
    """Parse a label from :func:`opaque_exam_label` back to a 0-based index.

    Raises
    ------
    ValueError
        If *label* is not exactly ``Exam N`` for an integer ``N >= 1``.
    """
    if not isinstance(label, str):
        raise ValueError("exam label must be a string")
    prefix = "Exam "
    if not label.startswith(prefix):
        raise ValueError("exam label is not an opaque Exam N label")
    suffix = label[len(prefix) :]
    if not suffix.isdigit():
        raise ValueError("exam label is not an opaque Exam N label")
    number = int(suffix)
    if number < 1:
        raise ValueError("exam label is not an opaque Exam N label")
    return number - 1


def resolve_loaded_exam_index(exam_id: str, *, result_index: int, n_loaded: int) -> int | None:
    """Map a multi-exam result row back onto the full loaded-input list.

    Successful ``MultiExamResult.exams`` omit excluded exams, so enumerating that
    list is **not** aligned with ``loaded_exams`` / CLI ``inputs``. Prefer the
    opaque ``Exam N`` label (which encodes the original load index). Fall back to
    *result_index* only when the id is not opaque, for legacy/test callers.
    """
    try:
        index = opaque_exam_index(exam_id)
    except ValueError:
        index = result_index
    if 0 <= index < n_loaded:
        return index
    return None


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
