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

from contextlib import suppress
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from mypyskindose.privacy import safe_error_event

# File-sink bounds. The native-mode log is a diagnostic aid, not an audit trail:
# it is opened fresh each session (mode="w") and rotated so it cannot grow without
# bound or accumulate PHI-bearing lines across runs.
_LOG_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB per file
_LOG_BACKUP_COUNT = 3  # at most ~4 MiB total

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
        safe_error_event(logging.getLogger(_LOGGER_ROOT), "debug_configuration_read", exc, level=logging.WARNING)
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


def _file_handler_level() -> int:
    """DEBUG only when a debug category is explicitly enabled; INFO otherwise.

    Module loggers (``logging.getLogger(__name__)``) inherit the root's DEBUG
    level, so without this gate their DEBUG records — which can include file
    paths/names (PHI in clinical use) — would land in the file by default. The
    handler level keeps those out unless the operator opts into debug.
    """
    return logging.DEBUG if any(DEBUG_FLAGS.values()) else logging.INFO


def _purge_log_files(target: str) -> None:
    """Delete the log file and any rotated backups so each session starts fresh.

    RotatingFileHandler ignores ``mode="w"`` once ``maxBytes>0`` (it forces append
    so rotation works), so truncate-on-start is done by removing the files first.
    """
    base = Path(target)
    candidates = [base] + [base.with_name(f"{base.name}.{i}") for i in range(1, _LOG_BACKUP_COUNT + 1)]
    for path in candidates:
        with suppress(OSError):
            path.unlink(missing_ok=True)


def _add_file_handler(log_file: str | Path) -> None:
    """Attach a bounded, fresh-per-session file handler to the root logger.

    The log is purged on attach (no cross-session accumulation) and rotation caps
    total size at ``_LOG_MAX_BYTES * (_LOG_BACKUP_COUNT + 1)``.
    """
    root = logging.getLogger(_LOGGER_ROOT)
    # RotatingFileHandler stores baseFilename as os.path.abspath(filename); match that.
    target = os.path.abspath(log_file)
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == target:
            h.setLevel(_file_handler_level())  # keep level in sync if flags changed
            return
    _purge_log_files(target)
    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError as exc:
        safe_error_event(root, "diagnostic_log_open", exc, level=logging.WARNING)
        return
    if os.name == "posix":
        try:
            os.chmod(target, 0o600)
        except OSError:
            root.warning("Could not restrict permissions on diagnostic log file")
    file_handler.setLevel(_file_handler_level())
    file_handler.setFormatter(_FORMATTER)
    root.addHandler(file_handler)


def _refresh_file_handler_levels() -> None:
    """Re-apply the PHI-safe file level to any attached file handlers."""
    level = _file_handler_level()
    for h in logging.getLogger(_LOGGER_ROOT).handlers:
        if isinstance(h, logging.FileHandler):
            h.setLevel(level)


def set_debug_flag(category: str, value: bool) -> None:
    """Enable or disable a debug category at runtime."""
    DEBUG_FLAGS[category.upper()] = bool(value)
    _category_logger(category).setLevel(logging.DEBUG if value else logging.INFO)
    # Keep the file sink's level in sync so a runtime toggle reaches the file.
    _refresh_file_handler_levels()


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
