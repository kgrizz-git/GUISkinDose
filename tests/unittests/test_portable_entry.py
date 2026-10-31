"""Tests for the portable (frozen) entry's log sink pieces.

Covers ``guiskindose.debug.default_native_log_path`` and the stdlib-only
``_LogStream`` in ``packaging/portable/entry.py`` that replaces a ``None``
stdout/stderr in a windowed build. The entry is loaded from its file; it does
not import nicegui at module level.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import types
from pathlib import Path

import pytest

from guiskindose import debug as dbg

_ENTRY = Path(__file__).resolve().parents[2] / "packaging" / "portable" / "entry.py"


@pytest.fixture(scope="module")
def entry_module():
    spec = importlib.util.spec_from_file_location("guiskindose_portable_entry", _ENTRY)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def captured_root():
    """Give the guiskindose logger one list handler; restore afterwards."""
    root = logging.getLogger("guiskindose")
    saved = root.handlers[:], root.level, root.propagate

    class _ListHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__(logging.DEBUG)
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    handler = _ListHandler()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG)
    root.propagate = False
    yield handler
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    root.propagate = saved[2]


def test_default_native_log_path_is_private_temp_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(dbg.tempfile, "gettempdir", lambda: str(tmp_path))
    path = dbg.default_native_log_path()
    assert path is not None
    assert path.name == "guiskindose-native.log"
    assert path.parent.parent == tmp_path
    if os.name == "posix":
        assert path.parent.name == f"guiskindose-{os.getuid()}"
        assert path.parent.stat().st_mode & 0o077 == 0


def test_default_native_log_path_returns_none_when_folder_unusable(monkeypatch, tmp_path):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(dbg.tempfile, "gettempdir", lambda: str(blocker))
    result = dbg.default_native_log_path()
    assert result is None


def _expected_folder(tmp_path: Path) -> Path:
    getuid = getattr(os, "getuid", None)
    return tmp_path / (f"guiskindose-{getuid()}" if getuid is not None else "guiskindose")


def test_default_native_log_path_refuses_symlinked_folder(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    try:
        _expected_folder(tmp_path).symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable for this user")
    monkeypatch.setattr(dbg.tempfile, "gettempdir", lambda: str(tmp_path))
    result = dbg.default_native_log_path()
    assert result is None


def test_default_native_log_path_refuses_file_in_folder_place(monkeypatch, tmp_path):
    _expected_folder(tmp_path).write_text("not a folder", encoding="utf-8")
    monkeypatch.setattr(dbg.tempfile, "gettempdir", lambda: str(tmp_path))
    result = dbg.default_native_log_path()
    assert result is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_default_native_log_path_tightens_existing_folder(monkeypatch, tmp_path):
    folder = _expected_folder(tmp_path)
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    monkeypatch.setattr(dbg.tempfile, "gettempdir", lambda: str(tmp_path))
    result = dbg.default_native_log_path()
    assert result == folder / "guiskindose-native.log"
    assert folder.stat().st_mode & 0o777 == 0o700


def test_log_stream_text_attributes(entry_module):
    stream = entry_module._LogStream("guiskindose.stdout", logging.INFO)
    assert stream.encoding == "utf-8"
    assert stream.errors == "replace"
    stream.reconfigure(encoding="ascii", line_buffering=True)  # no-op, must not raise
    assert stream.encoding == "utf-8"


def test_log_stream_forwards_complete_lines(entry_module, captured_root):
    stream = entry_module._LogStream("guiskindose.stdout", logging.INFO)
    print("Port 8765 is in use;", "using 8766", file=stream)
    stream.write("partial")
    assert [r.getMessage() for r in captured_root.records] == ["Port 8765 is in use; using 8766"]
    assert captured_root.records[0].levelno == logging.INFO
    stream.write(" line\n")
    assert captured_root.records[-1].getMessage() == "partial line"


def test_log_stream_drops_output_without_handlers(entry_module):
    root = logging.getLogger("guiskindose")
    saved = root.handlers[:]
    root.handlers.clear()
    try:
        stream = entry_module._LogStream("guiskindose.stderr", logging.DEBUG)
        written = stream.write("window child noise\n")
        assert written == len("window child noise\n")
    finally:
        root.handlers[:] = saved


def test_log_stream_breaks_handler_feedback_loop(entry_module):
    """A handler that writes back into the stream must not recurse."""
    root = logging.getLogger("guiskindose")
    saved = root.handlers[:], root.level, root.propagate
    stream = entry_module._LogStream("guiskindose.stdout", logging.INFO)
    echo = logging.StreamHandler(stream)
    root.handlers[:] = [echo]
    root.setLevel(logging.DEBUG)
    root.propagate = False
    try:
        stream.write("hello\n")  # would recurse forever without the per-thread guard
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
        root.propagate = saved[2]


def test_log_stream_flush_emits_pending_text(entry_module, captured_root):
    stream = entry_module._LogStream("guiskindose.stdout", logging.INFO)
    stream.write("no newline yet")
    assert captured_root.records == []
    stream.flush()
    assert [r.getMessage() for r in captured_root.records] == ["no newline yet"]
    stream.flush()  # nothing pending: no duplicate record
    assert len(captured_root.records) == 1


@pytest.fixture
def fake_dispatch(entry_module, monkeypatch):
    """Stub the file log, the GUI, and the ``selfcheck`` module; record what main() reaches."""
    calls: list[tuple] = []
    monkeypatch.setattr(entry_module, "_configure_file_log", lambda: calls.append(("log",)))
    fake = types.ModuleType("selfcheck")
    monkeypatch.setattr(
        fake, "run_self_check", lambda out, *, process_start: calls.append(("self_check", out)) or 0, raising=False
    )
    monkeypatch.setattr(fake, "run_network_probe", lambda out: calls.append(("network_probe", out)) or 0, raising=False)
    monkeypatch.setitem(sys.modules, "selfcheck", fake)
    fake_app = types.ModuleType("guiskindose.gui.app")
    monkeypatch.setattr(fake_app, "run_gui", lambda native: calls.append(("gui", native)), raising=False)
    monkeypatch.setitem(sys.modules, "guiskindose.gui.app", fake_app)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    return calls


@pytest.mark.parametrize(
    "argv",
    [["--self-check"], ["--network-probe"], ["--self-check", ""], ["--network-probe", ""], ["--self-check", "   "]],
)
def test_headless_flag_without_directory_fails_closed(entry_module, fake_dispatch, argv):
    # A local handler on the portable logger keeps this independent of test order:
    # an earlier configure_logging() turns off propagation from ``guiskindose``.
    portable = logging.getLogger("guiskindose.portable")
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collect(logging.ERROR)
    portable.addHandler(handler)
    try:
        code = entry_module.main(argv)
    finally:
        portable.removeHandler(handler)
    assert code == 2
    messages = [r.getMessage() for r in records]
    assert messages == [f"{argv[0]} requires an output directory"]
    assert fake_dispatch == [("log",)]


def test_self_check_flag_dispatches(entry_module, fake_dispatch):
    code = entry_module.main(["--self-check", "out-dir"])
    assert code == 0
    assert fake_dispatch == [("log",), ("self_check", "out-dir")]


def test_network_probe_flag_dispatches(entry_module, fake_dispatch):
    code = entry_module.main(["--network-probe", "probe-dir"])
    assert code == 0
    assert fake_dispatch == [("log",), ("network_probe", "probe-dir")]


def test_no_arguments_start_the_gui(entry_module, fake_dispatch):
    code = entry_module.main([])
    assert code == 0
    assert fake_dispatch[-1][0] == "gui"
    assert ("self_check", "") not in fake_dispatch


def test_calculate_and_export_overwrites_its_own_files_on_rerun(tmp_path, monkeypatch):
    """A second self-check in the same directory replaces the files it wrote."""
    monkeypatch.syspath_prepend(str(_ENTRY.parent))
    selfcheck = importlib.import_module("selfcheck")
    owned = tmp_path / selfcheck.OWNED_SUBDIR
    owned.mkdir()
    first = selfcheck._calculate_and_export(owned)
    second = selfcheck._calculate_and_export(owned)
    assert second["psd_mGy"] == first["psd_mGy"]
    names = sorted(p.name for p in owned.iterdir())
    assert names == ["selfcheck.html", "selfcheck.json", "selfcheck_dose_map.csv"]


def test_outputs_stay_inside_the_owned_subfolder(tmp_path, monkeypatch):
    """A same-named file already in the named directory is left alone."""
    import urllib.request

    monkeypatch.syspath_prepend(str(_ENTRY.parent))
    selfcheck = importlib.import_module("selfcheck")

    def _refuse(*_args, **_kwargs):
        raise OSError("blocked in test")

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    bystander = tmp_path / "network_probe.json"
    bystander.write_text("user file", encoding="utf-8")
    code = selfcheck.run_network_probe(str(tmp_path))
    assert code == 0
    assert bystander.read_text(encoding="utf-8") == "user file"
    report = tmp_path / selfcheck.OWNED_SUBDIR / "network_probe.json"
    assert '"outbound_blocked": true' in report.read_text(encoding="utf-8")


def test_launch_token_is_redacted_in_the_file_log(entry_module, tmp_path):
    """Browser mode prints its token URL; the file sink must never hold the token value."""
    root = logging.getLogger("guiskindose")
    saved = root.handlers[:], root.level, root.propagate
    log_file = tmp_path / "native.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    root.handlers[:] = [file_handler]
    root.setLevel(logging.DEBUG)
    root.propagate = False
    sample_value = "placeholder-0123-abcd"
    try:
        stream = entry_module._LogStream("guiskindose.stdout", logging.INFO)
        print(f"GUISkinDose GUI: open http://127.0.0.1:8765/?token={sample_value}", file=stream)
        print(f"retry http://127.0.0.1:8765/?a=1&token={sample_value}#x", file=stream)
    finally:
        file_handler.close()
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])
        root.propagate = saved[2]
    text = log_file.read_text(encoding="utf-8")
    assert sample_value not in text
    assert text.count("token=<redacted>") == 2
    assert "http://127.0.0.1:8765/?token=<redacted>" in text


def test_redact_launch_token_leaves_other_text_alone(entry_module):
    line = "NiceGUI ready to go on http://127.0.0.1:8765"
    assert entry_module.redact_launch_token(line) == line
