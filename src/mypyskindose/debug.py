"""Logging and debug configuration for MyPySkinDose.

Historically this module exposed ``dprint(category, *args)``, a flag-gated
``print``. It is now a thin shim over the standard library ``logging`` framework:

* Each debug *category* (GUI/PROCESSING/CALCULATION/RENDERING) maps to a child
  logger ``mypyskindose.<category>``. ``dprint`` emits at DEBUG level on that
  logger, so existing call sites keep working unchanged while output flows
  through ``logging`` (enabling levels, formatting, and file sinks).
* ``configure_logging()`` sets up the ``mypyskindose`` logger tree (console plus
  an optional file handler). This also lights up the many modules that already
  call ``logging.getLogger(__name__)`` but previously had no handler configured.

Call ``configure_logging()`` once at startup (the CLI and ``run_gui`` do this).
``dprint`` also lazily configures console logging on first use so debug output
is never silently dropped.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

# Debug categories — each maps to a child logger ``mypyskindose.<category>``.
DEBUG_FLAGS = {
    "GUI": False,
    "PROCESSING": False,
    "CALCULATION": False,
    "RENDERING": False,
}

_LOGGER_ROOT = "mypyskindose"
_configured = False


def _category_logger(category: str) -> logging.Logger:
    """Return the child logger for a debug category."""
    return logging.getLogger(f"{_LOGGER_ROOT}.{category.upper()}")


def _load_debug_json() -> None:
    """Read debug.json from the working directory into DEBUG_FLAGS, if present."""
    debug_file = Path("debug.json")
    if not debug_file.exists():
        return
    try:
        with open(debug_file, "r", encoding="utf-8") as f:
            user_flags = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger(_LOGGER_ROOT).warning("Could not read %s: %s", debug_file, exc)
        return
    for key, value in user_flags.items():
        if key.upper() in DEBUG_FLAGS:
            DEBUG_FLAGS[key.upper()] = bool(value)


def _apply_flag_levels() -> None:
    """Set each category logger's level from DEBUG_FLAGS (DEBUG if enabled)."""
    for category, enabled in DEBUG_FLAGS.items():
        _category_logger(category).setLevel(logging.DEBUG if enabled else logging.INFO)


def configure_logging(log_file: str | Path | None = None, *, force: bool = False) -> None:
    """Configure the ``mypyskindose`` logger tree. Idempotent unless *force*.

    Parameters
    ----------
    log_file:
        If given, also write logs to this file. Useful in native GUI mode,
        which has no console to read messages from.
    force:
        Reconfigure even if already configured (re-reads debug.json, re-applies
        levels, and adds the file handler if one is requested).
    """
    global _configured
    if _configured and not force:
        if log_file is not None:
            _add_file_handler(log_file)
        return

    _load_debug_json()

    root = logging.getLogger(_LOGGER_ROOT)
    root.setLevel(logging.DEBUG)  # children gate via their own levels
    root.propagate = False

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(_FORMATTER)
        root.addHandler(console)

    if log_file is not None:
        _add_file_handler(log_file)

    _apply_flag_levels()
    _configured = True


_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
)


def _add_file_handler(log_file: str | Path) -> None:
    """Attach a file handler to the root logger if not already present."""
    root = logging.getLogger(_LOGGER_ROOT)
    # FileHandler stores baseFilename as os.path.abspath(filename); match that.
    target = os.path.abspath(log_file)
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == target:
            return
    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
    except OSError as exc:
        root.warning("Could not open log file %s: %s", log_file, exc)
        return
    file_handler.setFormatter(_FORMATTER)
    root.addHandler(file_handler)


def set_debug_flag(category: str, value: bool) -> None:
    """Enable or disable a debug category at runtime."""
    DEBUG_FLAGS[category.upper()] = bool(value)
    _category_logger(category).setLevel(logging.DEBUG if value else logging.INFO)


def dprint(category: str, *args, **kwargs) -> None:
    """Log a debug message under *category* (back-compat shim over logging).

    Previously printed ``[DEBUG - CATEGORY] ...`` only when the flag was set.
    Now routed through ``logging.getLogger('mypyskindose.<category>').debug()``;
    the category remains visible via the logger name in the log format. The
    message is gated by the category logger's level (DEBUG when the flag is on).
    """
    if not _configured:
        configure_logging()
    message = " ".join(str(a) for a in args)
    _category_logger(category).debug(message)
