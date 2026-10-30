"""Frozen entry point for the portable GUISkinDose app (PyInstaller).

This script is the program a frozen build runs. It lives outside ``src/`` so it
never ships in the wheel and the ``guiskindose`` console script keeps its own
CLI entry (``guiskindose.__main__:cli``).

Order matters (see ``dev-docs/plans/PORTABLE_APP_PLAN.md`` -> Freeze):

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
"""

from __future__ import annotations

import io
import logging
import multiprocessing
import os
import sys
import threading
import time

_PROCESS_START = time.perf_counter()

# Opt-out for shared machines: no diagnostic file is written when this is set.
NO_FILE_LOG_ENV = "GUISKINDOSE_NO_FILE_LOG"


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
        self._logger.log(self._level, "%s", line)

    def flush(self) -> None:
        """Emit any buffered text that has no trailing newline yet."""
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


def _native_window() -> bool:
    """Windows and macOS open the pywebview window; Linux v1 uses the browser."""
    return not sys.platform.startswith("linux")


_HEADLESS_FLAGS = ("--self-check", "--network-probe")


def main(argv: list[str]) -> int:
    """Run the GUI, or the headless self-check when ``--self-check DIR`` is given."""
    if argv and argv[0] in _HEADLESS_FLAGS and len(argv) < 2:
        # Fail closed: a missing directory must never fall through to the GUI.
        print(f"{argv[0]} requires an output directory.", file=sys.stderr)
        return 2
    _configure_file_log()
    logger = logging.getLogger("guiskindose.portable")
    if argv and argv[0] == "--self-check":
        from selfcheck import run_self_check

        return run_self_check(argv[1], process_start=_PROCESS_START)
    if argv and argv[0] == "--network-probe":
        from selfcheck import run_network_probe

        return run_network_probe(argv[1])

    from guiskindose.gui.app import run_gui
    from guiskindose.privacy import install_value_safe_excepthook

    install_value_safe_excepthook(logger, "portable_gui")
    logger.info("Portable GUI starting (frozen=%s)", bool(getattr(sys, "frozen", False)))
    run_gui(native=_native_window())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
