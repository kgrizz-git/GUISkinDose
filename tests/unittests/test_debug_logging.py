"""Unit tests for the logging shim in mypyskindose.debug (refactor plan Phase 0.2).

dprint() is now a back-compat shim over the stdlib logging framework. These
tests pin the contract: category gating, message format, file sink, handler
de-duplication, and debug.json loading — without depending on the repo's
tracked debug.json (tests chdir to a clean temp directory).
"""

from __future__ import annotations

import io
import json
import logging
import os

import pytest

from mypyskindose import debug as dbg


@pytest.fixture
def clean_logging(monkeypatch, tmp_path):
    """Reset the mypyskindose logger tree and run from a debug.json-free cwd."""
    monkeypatch.chdir(tmp_path)
    root = logging.getLogger("mypyskindose")
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_propagate = root.propagate
    saved_flags = dict(dbg.DEBUG_FLAGS)
    saved_configured = dbg._configured

    root.handlers.clear()
    for cat in dbg.DEBUG_FLAGS:
        dbg.DEBUG_FLAGS[cat] = False
    dbg._configured = False

    yield root

    root.handlers.clear()
    root.handlers.extend(saved_handlers)
    root.setLevel(saved_level)
    root.propagate = saved_propagate
    dbg.DEBUG_FLAGS.clear()
    dbg.DEBUG_FLAGS.update(saved_flags)
    dbg._configured = saved_configured


def _capture(root: logging.Logger) -> io.StringIO:
    """Redirect the configured stream handler to a buffer and return it."""
    buf = io.StringIO()
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
            h.stream = buf
    return buf


def test_disabled_category_is_suppressed(clean_logging):
    dbg.configure_logging(force=True)
    buf = _capture(clean_logging)
    dbg.dprint("GUI", "hidden message")
    assert "hidden message" not in buf.getvalue()


def test_enabled_category_emits_with_name(clean_logging):
    dbg.configure_logging(force=True)
    buf = _capture(clean_logging)
    dbg.set_debug_flag("GUI", True)
    dbg.dprint("GUI", "visible", "joined", "args")
    out = buf.getvalue()
    assert "visible joined args" in out
    assert "mypyskindose.GUI" in out


def test_existing_module_logger_is_configured(clean_logging):
    """Modules that call getLogger(__name__) now have a handler via the tree."""
    dbg.configure_logging(force=True)
    buf = _capture(clean_logging)
    logging.getLogger("mypyskindose.rdsr_normalizer").warning("module level warning")
    assert "module level warning" in buf.getvalue()


def test_file_sink_writes(clean_logging, tmp_path):
    log_file = tmp_path / "gui.log"
    dbg.configure_logging(log_file=log_file, force=True)
    dbg.set_debug_flag("CALCULATION", True)
    dbg.dprint("CALCULATION", "to file")
    assert "to file" in log_file.read_text()


def test_file_handler_not_duplicated(clean_logging, tmp_path):
    log_file = tmp_path / "gui.log"
    dbg.configure_logging(log_file=log_file, force=True)
    dbg.configure_logging(log_file=log_file)  # idempotent second call
    n = sum(1 for h in clean_logging.handlers if isinstance(h, logging.FileHandler))
    assert n == 1


def test_debug_json_loaded_from_cwd(clean_logging, tmp_path):
    (tmp_path / "debug.json").write_text(json.dumps({"RENDERING": True}))
    dbg.configure_logging(force=True)
    assert dbg.DEBUG_FLAGS["RENDERING"] is True
    buf = _capture(clean_logging)
    dbg.dprint("RENDERING", "render msg")
    assert "render msg" in buf.getvalue()


def test_malformed_debug_json_does_not_raise(clean_logging, tmp_path):
    (tmp_path / "debug.json").write_text("{not valid json")
    # Should not raise; flags stay at their defaults.
    dbg.configure_logging(force=True)
    assert dbg.DEBUG_FLAGS["GUI"] is False


def test_dprint_lazily_configures(clean_logging):
    """dprint before configure_logging still sets up logging (no dropped setup)."""
    assert dbg._configured is False
    dbg.dprint("GUI", "anything")
    assert dbg._configured is True


# ── file sink: PHI-safe level, rotation, fresh-per-session ───────────────────
def test_file_handler_is_rotating_and_bounded(clean_logging, tmp_path):
    from logging.handlers import RotatingFileHandler

    log_file = tmp_path / "gui.log"
    dbg.configure_logging(log_file=log_file, force=True)
    fh = next(h for h in clean_logging.handlers if isinstance(h, logging.FileHandler))
    assert isinstance(fh, RotatingFileHandler)
    assert fh.maxBytes == dbg._LOG_MAX_BYTES
    assert fh.backupCount == dbg._LOG_BACKUP_COUNT


def test_module_debug_does_not_leak_to_file_by_default(clean_logging, tmp_path):
    """With no debug flag set, module-logger DEBUG (e.g. a file path) must not
    reach the file sink — the handler defaults to INFO."""
    log_file = tmp_path / "gui.log"
    dbg.configure_logging(log_file=log_file, force=True)
    logging.getLogger("mypyskindose.helpers.read_and_normalize_rdsr_data").debug(
        "SECRET /patients/Smith_MRN123.dcm"
    )
    logging.getLogger("mypyskindose.GUI").info("benign info")
    for h in clean_logging.handlers:
        h.flush()
    contents = log_file.read_text()
    assert "SECRET" not in contents
    assert "benign info" in contents


def test_enabling_flag_lets_debug_reach_file(clean_logging, tmp_path):
    """Opting into a debug category lowers the file sink to DEBUG at runtime."""
    log_file = tmp_path / "gui.log"
    dbg.configure_logging(log_file=log_file, force=True)
    dbg.set_debug_flag("CALCULATION", True)
    dbg.dprint("CALCULATION", "calc debug detail")
    for h in clean_logging.handlers:
        h.flush()
    assert "calc debug detail" in log_file.read_text()


def test_file_sink_purged_on_new_session(clean_logging, tmp_path):
    """Each configure_logging(log_file=...) starts a fresh file and drops backups."""
    log_file = tmp_path / "gui.log"
    log_file.write_text("STALE FROM A PRIOR SESSION\n")
    (tmp_path / "gui.log.1").write_text("old rotated backup\n")

    dbg.configure_logging(log_file=log_file, force=True)

    assert "STALE" not in log_file.read_text()
    assert not (tmp_path / "gui.log.1").exists()


def test_file_sink_is_owner_only_on_posix(clean_logging, tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX file mode bits are not portable to this platform")
    log_file = tmp_path / "gui.log"
    dbg.configure_logging(log_file=log_file, force=True)

    assert log_file.stat().st_mode & 0o077 == 0
