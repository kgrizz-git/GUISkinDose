"""Tests for the portable (frozen) entry's log sink pieces.

Covers ``guiskindose.debug.default_native_log_path`` and the stdlib-only
``_LogStream`` in ``packaging/portable/entry.py`` that replaces a ``None``
stdout/stderr in a windowed build. The entry is loaded from its file; it does
not import nicegui at module level.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import logging
import multiprocessing
import os
import signal
import subprocess
import sys
import types
from pathlib import Path

import pytest

from guiskindose import debug as dbg

_ENTRY = Path(__file__).resolve().parents[2] / "packaging" / "portable"
_ENTRY_FILE = _ENTRY / "entry.py"
_ENTRY_MODULE_NAME = "guiskindose_portable_entry"


def _load_entry_module(*, argv: list[str] | None = None) -> types.ModuleType:
    """Import ``entry.py`` fresh so import-time gates see the given ``argv``."""
    saved_argv = sys.argv[:]
    sys.path.insert(0, str(_ENTRY))
    try:
        if argv is not None:
            sys.argv = argv
        sys.modules.pop(_ENTRY_MODULE_NAME, None)
        spec = importlib.util.spec_from_file_location(_ENTRY_MODULE_NAME, _ENTRY_FILE)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.argv = saved_argv
        with contextlib.suppress(ValueError):
            sys.path.remove(str(_ENTRY))


@pytest.fixture(scope="module")
def entry_module():
    return _load_entry_module(argv=[str(_ENTRY_FILE)])


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
    [
        ["--self-check"],
        ["--network-probe"],
        ["--png-check"],
        ["--self-check", ""],
        ["--network-probe", ""],
        ["--png-check", ""],
        ["--self-check", "   "],
        ["--png-check", "   "],
    ],
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


def test_png_check_flag_dispatches(entry_module, fake_dispatch, monkeypatch, tmp_path):
    fake = types.ModuleType("pngcheck")
    monkeypatch.setattr(
        fake,
        "run_png_check",
        lambda out, *, process_start: fake_dispatch.append(("png_check", out, process_start)) or 0,
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "pngcheck", fake)
    code = entry_module.main(["--png-check", str(tmp_path)])
    assert code == 0
    assert fake_dispatch == [("log",), ("png_check", str(tmp_path), entry_module._PROCESS_START)]


def test_no_arguments_start_the_gui(entry_module, fake_dispatch):
    code = entry_module.main([])
    assert code == 0
    assert fake_dispatch[-1][0] == "gui"
    assert ("self_check", "") not in fake_dispatch


def test_calculate_and_export_overwrites_its_own_files_on_rerun(tmp_path, monkeypatch):
    """A second self-check in the same directory replaces the files it wrote."""
    monkeypatch.syspath_prepend(str(_ENTRY))
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

    monkeypatch.syspath_prepend(str(_ENTRY))
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


def test_quiet_browser_loggers_silence_info_records(entry_module):
    names = ("choreographer", "kaleido", "logistro")
    saved = {name: logging.getLogger(name).level for name in names}
    try:
        entry_module._quiet_browser_loggers()
        child = logging.getLogger("choreographer.browsers.chromium")
        assert not child.isEnabledFor(logging.INFO)
        assert child.isEnabledFor(logging.WARNING)
        assert not logging.getLogger("kaleido.kaleido").isEnabledFor(logging.INFO)
        assert not logging.getLogger("logistro").isEnabledFor(logging.INFO)
    finally:
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


def test_main_quiets_browser_loggers_before_dispatch(entry_module, fake_dispatch, monkeypatch):
    monkeypatch.setattr(entry_module, "_quiet_browser_loggers", lambda: fake_dispatch.append(("quiet",)))
    entry_module.main([])
    assert [call[0] for call in fake_dispatch] == ["log", "quiet", "gui"]


def test_choreographer_unix_pipe_wrapper_drift() -> None:
    """Installed choreographer must still match the bootloader gate protocol."""
    import choreographer

    root = Path(choreographer.__file__).resolve().parent
    wrapper = (root / "browsers" / "_unix_pipe_chromium_wrapper.py").read_text(encoding="utf-8")
    assert "os.dup2(0, 3)" in wrapper
    assert "os.dup2(1, 4)" in wrapper
    assert "pass_fds=(3, 4)" in wrapper
    assert 'print("{bye}")' in wrapper

    pipe_source = (root / "channels" / "pipe.py").read_text(encoding="utf-8")
    assert 'b"{bye}\\n"' in pipe_source

    chromium_source = (root / "browsers" / "chromium.py").read_text(encoding="utf-8")
    assert "sys.executable" in chromium_source
    assert "_unix_pipe_chromium_wrapper.py" in chromium_source
    off_windows = chromium_source.split('if platform.system() != "Windows":', 1)[1].split("else:", 1)[0]
    assert "sys.executable" in off_windows
    assert "_chromium_wrapper_path" in off_windows


@pytest.fixture
def unix_host(monkeypatch):
    """Run the gate as on macOS or Linux, also on the Windows CI leg."""
    monkeypatch.syspath_prepend(str(_ENTRY))
    monkeypatch.setattr(importlib.import_module("_entry_platform"), "_override", "linux")


def _wrapper_argv(tmp_path: Path, *, browser_name: str = "chrome") -> list[str]:
    exe = tmp_path / "GUISkinDose"
    exe.write_text("", encoding="utf-8")
    wrapper = tmp_path / "_unix_pipe_chromium_wrapper.py"
    wrapper.write_text("", encoding="utf-8")
    browser = tmp_path / "chromium" / browser_name
    browser.parent.mkdir(parents=True, exist_ok=True)
    browser.write_text("", encoding="utf-8")
    return [str(exe), str(wrapper), str(browser), "--headless"]


def test_unix_wrapper_gate_dup2_popen_and_bye(unix_host, monkeypatch, tmp_path, captured_root):
    dup2_calls: list[tuple[int, int]] = []
    inheritable: list[tuple[int, bool]] = []
    popen_calls: dict[str, object] = {}
    write_calls: list[tuple[int, bytes]] = []

    class _FakeProcess:
        returncode = 0
        terminated = 0

        def terminate(self) -> None:
            self.terminated += 1

        def wait(self, timeout: float | None = None) -> int:
            if timeout is not None:
                return 0
            return 0

        def kill(self) -> None:
            return

    launched: list[_FakeProcess] = []
    handlers: dict[int, object] = {}

    def _fake_popen(cli: list[str], **kwargs: object) -> _FakeProcess:
        popen_calls["cli"] = cli
        popen_calls["kwargs"] = kwargs
        launched.append(_FakeProcess())
        return launched[-1]

    real_fstat = os.fstat

    def _free_debug_fds(fd: int) -> object:
        if fd in (3, 4):
            raise OSError
        return real_fstat(fd)

    monkeypatch.setattr(os, "dup2", lambda src, dst: dup2_calls.append((src, dst)))
    monkeypatch.setattr(os, "set_inheritable", lambda fd, val: inheritable.append((fd, val)))
    monkeypatch.setattr(os, "fstat", _free_debug_fds)
    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(os, "write", lambda fd, data: write_calls.append((fd, data)) or len(data))
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))

    argv = _wrapper_argv(tmp_path)
    monkeypatch.setattr(sys, "executable", argv[0])
    with pytest.raises(SystemExit) as exc:
        _load_entry_module(argv=argv)
    assert exc.value.code == 0
    assert dup2_calls == [(0, 3), (1, 4)]
    assert set(inheritable) == {(3, True), (4, True)}
    assert popen_calls["cli"] == [argv[2], "--headless"]
    assert popen_calls["kwargs"] == {"pass_fds": (3, 4)}
    assert write_calls == [(1, b"{bye}\n")]
    assert not any(argv[2] in r.getMessage() for r in captured_root.records)
    assert set(handlers) == {signal.SIGTERM, signal.SIGINT}
    for handler in handlers.values():
        handler(signal.SIGTERM, None)  # type: ignore[operator]
    assert launched[0].terminated == 1  # one terminate per shutdown, however many signals


def test_unix_wrapper_gate_short_argv_does_not_touch_argv_or_dup2(monkeypatch, tmp_path):
    dup2_called = False
    popen_called = False

    def _dup2(*_args: object) -> None:
        nonlocal dup2_called
        dup2_called = True

    def _popen(*_args: object, **_kwargs: object) -> object:
        nonlocal popen_called
        popen_called = True
        raise AssertionError("Popen must not run")

    monkeypatch.setattr(os, "dup2", _dup2)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "exe"))
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "exe"), "only-two"])  # argv[2] would raise IndexError
    module = _load_entry_module()
    assert module is not None
    assert not dup2_called
    assert not popen_called


def test_unix_wrapper_gate_rejects_browser_outside_chromium(unix_host, monkeypatch, tmp_path):
    dup2_called = False
    popen_called = False
    outside = tmp_path / "evil-chrome"
    outside.write_text("", encoding="utf-8")
    argv = _wrapper_argv(tmp_path)
    argv[2] = str(outside)

    def _dup2(*_args: object) -> None:
        nonlocal dup2_called
        dup2_called = True

    def _popen(*_args: object, **_kwargs: object) -> object:
        nonlocal popen_called
        popen_called = True
        raise AssertionError("Popen must not run")

    monkeypatch.setattr(os, "dup2", _dup2)
    monkeypatch.setattr(subprocess, "Popen", _popen)
    monkeypatch.setattr(sys, "executable", argv[0])
    with pytest.raises(SystemExit) as exc:
        _load_entry_module(argv=argv)
    assert exc.value.code == 1
    assert not dup2_called
    assert not popen_called


class _SlowProcess:
    """Ignores terminate(); only kill() ends it."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        if self.killed:
            return -9
        if timeout is None:
            raise AssertionError("an unbounded wait before kill would hang")
        raise subprocess.TimeoutExpired(cmd=["chrome"], timeout=timeout)

    def kill(self) -> None:
        self.killed = True


def test_signal_handler_only_terminates(entry_module):
    proc = _SlowProcess()
    requested: list[float] = []
    entry_module._terminate_chromium_on_signal([proc], requested, signal.SIGTERM, None)
    assert proc.terminated
    assert not proc.killed
    assert len(requested) == 1
    assert requested[0] != float("inf")


def test_signal_handler_claims_shutdown_before_terminating(entry_module):
    """A signal that lands inside the handler, during terminate(), must not terminate again."""
    requested: list[float] = []
    calls: list[int] = []

    class _Reentrant:
        def terminate(self) -> None:
            calls.append(1)
            entry_module._terminate_chromium_on_signal([self], requested, signal.SIGINT, None)

    entry_module._terminate_chromium_on_signal([_Reentrant()], requested, signal.SIGTERM, None)
    assert calls == [1]
    assert len(requested) == 1


def test_signal_before_launch_is_recorded_without_a_process(entry_module):
    requested: list[float] = []
    entry_module._terminate_chromium_on_signal([], requested, signal.SIGTERM, None)
    assert len(requested) == 1


def test_wait_kills_chromium_after_the_grace_period(entry_module, monkeypatch):
    monkeypatch.setattr(entry_module, "_TERMINATE_GRACE_S", 0.0)
    proc = _SlowProcess()
    assert entry_module._wait_for_chromium(proc, [0.0]) == -9
    assert proc.killed


def test_wait_without_a_signal_keeps_waiting(entry_module):
    class _ExitsOnThirdPoll:
        polls = 0

        def wait(self, timeout: float | None = None) -> int:
            self.polls += 1
            if self.polls < 3:
                raise subprocess.TimeoutExpired(cmd=["chrome"], timeout=timeout or 0)
            return 0

        def kill(self) -> None:
            raise AssertionError("no signal, so no kill")

    assert entry_module._wait_for_chromium(_ExitsOnThirdPoll(), []) == 0


def test_unix_wrapper_gate_resolution_failure_is_silent(unix_host, monkeypatch, tmp_path):
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    argv = _wrapper_argv(tmp_path)
    monkeypatch.setattr(sys, "executable", argv[0])

    def _boom(self: Path, *_a: object, **_k: object) -> Path:
        raise OSError("resolve failed")

    monkeypatch.setattr(Path, "resolve", _boom)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("Popen must not run"))
    with pytest.raises(SystemExit) as exc:
        _load_entry_module(argv=argv)
    assert exc.value.code == 1
    assert stderr.getvalue() == ""


def test_wrapper_gate_is_no_op_on_win32(monkeypatch, tmp_path):
    import importlib

    dup2_called = False

    def _dup2(*_args: object) -> None:
        nonlocal dup2_called
        dup2_called = True

    monkeypatch.syspath_prepend(str(_ENTRY))
    entry_platform = importlib.import_module("_entry_platform")
    monkeypatch.setattr(entry_platform, "_override", "win32")
    monkeypatch.setattr(os, "dup2", _dup2)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("Popen must not run"))
    argv = _wrapper_argv(tmp_path)
    monkeypatch.setattr(sys, "executable", argv[0])
    module = _load_entry_module(argv=argv)
    assert module is not None
    assert not dup2_called


def test_unix_wrapper_gate_rejects_open_debugging_fds(unix_host, monkeypatch, tmp_path):
    dup2_called = False
    fstat_calls: list[int] = []

    def _dup2(*_args: object) -> None:
        nonlocal dup2_called
        dup2_called = True

    real_fstat = os.fstat

    def _fstat(fd: int) -> object:
        fstat_calls.append(fd)
        if fd == 3:
            return real_fstat(0)
        raise OSError

    monkeypatch.setattr(os, "fstat", _fstat)
    monkeypatch.setattr(os, "dup2", _dup2)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("Popen must not run"))
    argv = _wrapper_argv(tmp_path)
    monkeypatch.setattr(sys, "executable", argv[0])
    with pytest.raises(SystemExit) as exc:
        _load_entry_module(argv=argv)
    assert exc.value.code == 1
    assert 3 in fstat_calls
    assert not dup2_called


def test_unix_wrapper_gate_suppresses_traceback_on_popen_failure(unix_host, monkeypatch, tmp_path):
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)

    def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("must not reach choreographer")

    real_fstat = os.fstat

    def _free_debug_fds(fd: int) -> object:
        if fd in (3, 4):
            raise OSError
        return real_fstat(fd)

    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(os, "fstat", _free_debug_fds)
    monkeypatch.setattr(os, "dup2", lambda *_a: None)
    monkeypatch.setattr(os, "set_inheritable", lambda *_a: None)
    monkeypatch.setattr(signal, "signal", lambda *_a: None)
    argv = _wrapper_argv(tmp_path)
    monkeypatch.setattr(sys, "executable", argv[0])
    with pytest.raises(SystemExit) as exc:
        _load_entry_module(argv=argv)
    assert exc.value.code == 1
    assert stderr.getvalue() == ""


def test_normal_import_still_calls_freeze_support(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(multiprocessing, "freeze_support", lambda: calls.append(True))
    _load_entry_module(argv=[str(_ENTRY_FILE)])
    assert calls == [True]


def test_signal_during_launch_terminates_chromium_once_it_exists(unix_host, monkeypatch, tmp_path):
    """Handlers are installed before Popen; a signal that lands first still ends Chromium."""
    handlers: dict[int, object] = {}

    class _Proc:
        terminated = 0

        def terminate(self) -> None:
            self.terminated += 1

        def wait(self, timeout: float | None = None) -> int:
            return 0

    procs: list[_Proc] = []

    def _popen(*_a: object, **_k: object) -> _Proc:
        assert set(handlers) == {signal.SIGTERM, signal.SIGINT}  # installed before the launch
        handlers[signal.SIGTERM](signal.SIGTERM, None)  # type: ignore[operator]
        procs.append(_Proc())
        return procs[-1]

    real_fstat = os.fstat

    def _free_debug_fds(fd: int) -> object:
        if fd in (3, 4):
            raise OSError
        return real_fstat(fd)

    monkeypatch.setattr(os, "fstat", _free_debug_fds)
    monkeypatch.setattr(os, "dup2", lambda *_a: None)
    monkeypatch.setattr(os, "set_inheritable", lambda *_a: None)
    monkeypatch.setattr(os, "write", lambda _fd, data: len(data))
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
    monkeypatch.setattr(subprocess, "Popen", _popen)
    argv = _wrapper_argv(tmp_path)
    monkeypatch.setattr(sys, "executable", argv[0])
    with pytest.raises(SystemExit) as exc:
        _load_entry_module(argv=argv)
    assert exc.value.code == 0
    assert procs[0].terminated == 1
