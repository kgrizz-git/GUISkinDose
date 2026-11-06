"""Frozen entry point for the portable GUISkinDose app (PyInstaller).

This script is the program a frozen build runs. It lives outside ``src/`` so it
never ships in the wheel and the ``guiskindose`` console script keeps its own
CLI entry (``guiskindose.__main__:cli``).

Order matters (see ``dev-docs/plans/PORTABLE_APP_PLAN.md`` -> Freeze):

0. On Unix, choreographer re-execs the frozen bootloader with
   ``_unix_pipe_chromium_wrapper.py`` in ``argv[1]``. The entry performs that
   wrapper body before anything touches fd 1 (see
   ``dev-docs/plans/PORTABLE_BROWSER_WRAPPER_PLAN.md``).
1. A windowed build has no console, so ``sys.stdout`` / ``sys.stderr`` can be
   ``None``. They are pointed at the log sink first, using only the standard
   library, so nothing below writes to ``None``.
2. ``multiprocessing.freeze_support()`` runs next, before any project import.
   NiceGUI starts the native window in a child process that re-executes this
   program with ``--multiprocessing-fork``; ``freeze_support`` hands that child
   to multiprocessing instead of starting a second GUI.
3. Only under ``__main__`` does it configure the file log and call ``run_gui``.
   ``--self-check <dir>`` instead runs the headless packaged-data and
   calculate/export check in ``selfcheck.py`` (used by CI; no network, no git).
   ``--network-probe <dir>`` makes one outbound HTTPS request so the spike
   workflow can prove its firewall rule blocks the exe.
   ``--png-check <dir>`` renders dose-map PNGs through the Chromium bundled in
   the onedir (Full shape only; see ``pngcheck.py``).
"""

from __future__ import annotations

import contextlib
import io
import logging
import multiprocessing
import os
import re
import signal
import subprocess
import sys
import threading
import time
from functools import partial
from pathlib import Path
from types import FrameType

_PROCESS_START = time.perf_counter()

# Beside this script, so it is on sys.path unfrozen and in the spec's pathex frozen.
import _entry_platform  # noqa: E402


def _host_platform() -> str:
    return _entry_platform.host_platform()


# Opt-out for shared machines: no diagnostic file is written when this is set.
NO_FILE_LOG_ENV = "GUISKINDOSE_NO_FILE_LOG"

# Browser mode (Linux) prints its launch URL with the per-launch token
# (``loopback_security.TOKEN_QUERY_PARAM``). That URL is a credential, so it must
# never reach the persistent log. The app opens the URL itself, so nothing is lost.
_TOKEN_QUERY = re.compile(r"([?&]token=)[^&#\s]+")


def redact_launch_token(text: str) -> str:
    """Replace any ``token=`` query value in *text* with ``<redacted>``."""
    return _TOKEN_QUERY.sub(r"\1<redacted>", text)


class _LogStream(io.TextIOBase):
    """Text stream that forwards complete lines to a ``guiskindose`` logger.

    Used only where the interpreter gave us no stream (windowed build). Output is
    dropped until the ``guiskindose`` logger tree has handlers, so a window child
    process (which never configures logging) stays silent. A per-thread guard
    drops writes that a handler makes back into this stream, which breaks the
    loop through the console handler.
    """

    def __init__(self, logger_name: str, level: int) -> None:
        super().__init__()
        self._logger = logging.getLogger(logger_name)
        self._level = level
        self._local = threading.local()

    # Libraries read these to decide what they may write.
    encoding = "utf-8"
    errors = "replace"

    def reconfigure(self, **_kwargs: object) -> None:
        """Accept ``sys.stdout.reconfigure(...)`` calls and ignore them."""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        local = self._local
        if getattr(local, "busy", False):
            return len(text)
        pending = getattr(local, "pending", "") + text
        *lines, local.pending = pending.split("\n")
        local.busy = True
        try:
            for line in lines:
                self._emit(line)
        finally:
            local.busy = False
        return len(text)

    def _emit(self, line: str) -> None:
        line = line.rstrip("\r")
        if not line.strip() or not logging.getLogger("guiskindose").handlers:
            return
        self._logger.log(self._level, "%s", redact_launch_token(line))

    def flush(self) -> None:
        """Emit any buffered text that has no trailing newline yet.

        ``pending`` is thread-local, so this flushes only the calling thread's buffer.
        """
        local = self._local
        pending = getattr(local, "pending", "")
        if getattr(local, "busy", False) or not pending:
            return
        local.pending = ""
        local.busy = True
        try:
            self._emit(pending)
        finally:
            local.busy = False


_WRAPPER_SCRIPT_SUFFIX = "_unix_pipe_chromium_wrapper.py"
_BYE_SENTINEL = b"{bye}\n"


def _chromium_path_allowed(exe_path: str, chromium_root: Path) -> bool:
    """True when *exe_path* resolves under *chromium_root* (same idea as ``pngcheck._inside``)."""
    if not exe_path:
        return False
    target = os.path.normcase(str(Path(exe_path).resolve()))
    root = os.path.normcase(str(chromium_root.resolve()))
    try:
        return os.path.commonpath([target, root]) == root
    except ValueError:
        return False


_TERMINATE_GRACE_S = 5.0
_WAIT_POLL_S = 0.2


def _terminate_chromium_on_signal(
    launched: list[subprocess.Popen[bytes]],
    claim: list[bool],
    requested: list[float],
    _sig_num: int,
    _frame: FrameType | None,
) -> None:
    """Ask Chromium to exit and note when. :func:`_wait_for_chromium` kills it after the grace period.

    The handler does no waiting itself, so the wrapper still reaches the ``{bye}`` write. ``claim``
    starts with one item, and ``list.pop`` is a single C call, so exactly one handler takes it: a
    signal that lands anywhere inside this handler returns at once. A signal that lands before
    Chromium starts is only recorded; :func:`_run_unix_pipe_chromium_wrapper` terminates Chromium
    right after launch.
    """
    try:
        claim.pop()
    except IndexError:
        return
    requested.append(time.monotonic())
    if launched:
        with contextlib.suppress(OSError):
            launched[0].terminate()


def _wait_for_chromium(process: subprocess.Popen[bytes], requested: list[float]) -> int:
    """Wait for Chromium; kill it when it outlives a signalled shutdown by ``_TERMINATE_GRACE_S``."""
    while True:
        try:
            return process.wait(timeout=_WAIT_POLL_S)
        except subprocess.TimeoutExpired:
            if requested and time.monotonic() - requested[0] >= _TERMINATE_GRACE_S:
                return _kill_chromium(process)


def _kill_chromium(process: subprocess.Popen[bytes]) -> int:
    """Kill Chromium and wait a bounded time; ``1`` when it still has not exited."""
    with contextlib.suppress(OSError):
        process.kill()
    try:
        return process.wait(timeout=_TERMINATE_GRACE_S)
    except subprocess.TimeoutExpired:
        return 1


def _debugging_pipe_fds_free() -> bool:
    """True when fds 3 and 4 are not already open (choreographer expects to dup2 onto them)."""
    for fd in (3, 4):
        try:
            os.fstat(fd)
        except OSError:
            continue
        return False
    return True


def _run_unix_pipe_chromium_wrapper(cli: list[str]) -> int:
    """Hand stdin/stdout to Chromium on fds 3 and 4, wait, then write the pipe close sentinel."""
    if not _debugging_pipe_fds_free():
        raise SystemExit(1)

    os.dup2(0, 3)
    os.dup2(1, 4)
    os.set_inheritable(3, True)
    os.set_inheritable(4, True)

    # Handlers go in before the launch, so no signal can arrive while the default action
    # would end this wrapper and orphan Chromium. Blocking the signals instead would leave
    # them blocked in Chromium too, because a child inherits the signal mask.
    launched: list[subprocess.Popen[bytes]] = []
    claim = [True]
    requested: list[float] = []
    handler = partial(_terminate_chromium_on_signal, launched, claim, requested)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
    process = subprocess.Popen(cli, pass_fds=(3, 4))
    launched.append(process)
    if requested:  # a signal arrived before Chromium existed
        with contextlib.suppress(OSError):
            process.terminate()

    code = 1
    try:
        code = _wait_for_chromium(process, requested)
    finally:
        # Whatever went wrong, leave no Chromium holding fds 3 and 4, and tell choreographer.
        if process.poll() is None:
            _kill_chromium(process)
        with contextlib.suppress(OSError):
            os.write(1, _BYE_SENTINEL)
    return code


def _maybe_run_unix_pipe_chromium_wrapper() -> None:
    """Perform choreographer's Unix pipe-wrapper re-exec when ``argv`` matches."""
    if _host_platform() == "win32" or len(sys.argv) < 3:
        return
    if not sys.argv[1].endswith(_WRAPPER_SCRIPT_SUFFIX):
        return

    cli = sys.argv[2:]
    if not cli:
        raise SystemExit(1)

    try:
        chromium_root = Path(sys.executable).resolve().parent / "chromium"
        if not _chromium_path_allowed(cli[0], chromium_root):
            raise SystemExit(1)
        code = _run_unix_pipe_chromium_wrapper(cli)
    except SystemExit:
        raise
    except BaseException:
        raise SystemExit(1) from None
    raise SystemExit(code)


_maybe_run_unix_pipe_chromium_wrapper()


def _route_missing_streams() -> None:
    """Point ``None`` stdout/stderr at the log sink (windowed builds only).

    ``print`` output becomes INFO. Anything on stderr becomes DEBUG, because raw
    tracebacks and library warnings can carry file paths; it only reaches the
    file when an operator turns a debug category on.
    """
    if sys.stdout is None:
        sys.stdout = _LogStream("guiskindose.stdout", logging.INFO)
    if sys.stderr is None:
        sys.stderr = _LogStream("guiskindose.stderr", logging.DEBUG)


_route_missing_streams()
multiprocessing.freeze_support()


def _configure_file_log() -> None:
    """Attach the per-user temp-path log file unless the opt-out is set."""
    from guiskindose.debug import configure_logging, default_native_log_path

    log_path = None if os.environ.get(NO_FILE_LOG_ENV) else default_native_log_path()
    configure_logging(log_file=log_path)


def _quiet_browser_loggers() -> None:
    """Keep choreographer, kaleido and logistro at WARNING.

    Defense in depth. ``configure_logging`` attaches its handlers to the ``guiskindose`` logger only
    and sets ``propagate = False`` there, so browser records do not reach the file log today. The
    guard matters if something configures the root logger: choreographer calls
    ``logistro.betterConfig(level=1)`` when ``CHOREO_ENABLE_DEBUG`` is set, which puts a root handler
    on ``sys.stderr``. In a windowed build that stream feeds the file log, and the INFO record
    "Found chromium path: ..." would write the absolute browser path there.
    """
    for name in ("choreographer", "kaleido", "logistro"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _native_window() -> bool:
    """Windows and macOS open the pywebview window; Linux v1 uses the browser."""
    return not sys.platform.startswith("linux")


_HEADLESS_FLAGS = ("--self-check", "--network-probe", "--png-check")


def main(argv: list[str]) -> int:
    """Run the GUI, or the headless self-check when ``--self-check DIR`` is given."""
    _configure_file_log()
    _quiet_browser_loggers()
    logger = logging.getLogger("guiskindose.portable")
    if argv and argv[0] in _HEADLESS_FLAGS and (len(argv) < 2 or not argv[1].strip()):
        # Fail closed: a missing or blank directory must never fall through to the GUI.
        # Logged once: the console handler shows it in a console build, and the file
        # sink keeps it in a windowed build.
        logger.error("%s requires an output directory", argv[0])
        return 2
    if argv and argv[0] == "--self-check":
        from selfcheck import run_self_check

        return run_self_check(argv[1], process_start=_PROCESS_START)
    if argv and argv[0] == "--network-probe":
        from selfcheck import run_network_probe

        return run_network_probe(argv[1])
    if argv and argv[0] == "--png-check":
        from pngcheck import run_png_check

        return run_png_check(argv[1], process_start=_PROCESS_START)

    from guiskindose.gui.app import run_gui
    from guiskindose.privacy import install_value_safe_excepthook

    install_value_safe_excepthook(logger, "portable_gui")
    logger.info("Portable GUI starting (frozen=%s)", bool(getattr(sys, "frozen", False)))
    run_gui(native=_native_window())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
