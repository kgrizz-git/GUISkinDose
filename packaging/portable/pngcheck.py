"""Offline PNG check for a Full-shape frozen GUISkinDose build.

Run as ``GUISkinDose.exe --png-check <output dir>``. It renders the dose-map PNGs of
the bundled example RDSR through Kaleido, using only the Chromium copied into the
onedir under ``chromium/``. The render goes through the app's own PNG path,
``guiskindose.export.png_browser.figure_to_png``, which passes the bundled browser path to
Kaleido explicitly (choreographer would otherwise prefer a Chrome for Testing it downloaded
earlier, then ``BROWSER_PATH``, then a system install). Each image starts its own one-shot
browser, so one sampler thread watches process launches for the whole export. On Windows
that watch is one PowerShell process: starting a new one for every sample is slower than the
browser, and an empty sample still counted as a successful probe.

It fails unless:

- the bundled browser and its license notices are present,
- at least one PNG comes back,
- every browser process launched under this process runs from inside the onedir,
- the page Kaleido generated references no ``http(s)`` script URL.

The report ``pngcheck_report.json`` holds booleans, counts, flag names, and paths
relative to the onedir only: no absolute paths and no exam values. A passing render
includes ``samples`` and ``rows``. A failed render also stores a stable ``code``
(``browser_not_seen``, ``browser_outside``, ``browser_uninspectable``, or
``sampler_did_not_stop``) and integer ``counts`` when it has them. Those counts
are sample and process totals, never paths.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess  # nosec B404 - fixed argv, used only to list this process's children
import sys
import threading
import time
from pathlib import Path
from typing import Any

from selfcheck import _EXAMPLE_RDSR, OWNED_SUBDIR, _pkg, _run_step, _write_atomic

from guiskindose.export.png_browser import bundled_browser

# Notices that must sit beside the bundled browser (PORTABLE_CHROMIUM_ARTIFACT.md).
NOTICE_FILES = ("LICENSE.chromium.txt", "LICENSE.ungoogled-chromium-windows.txt", "CREDITS.html")
_MIN_CREDITS_BYTES = 100_000
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_HTTP_SCRIPT = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']?\s*https?:", re.IGNORECASE)


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _check_bundle() -> dict[str, Any]:
    browser = bundled_browser(app_dir())
    notices = {name: (browser.parent / name).is_file() for name in NOTICE_FILES}
    credits_path = browser.parent / "CREDITS.html"
    found = {
        "browser_present": browser.is_file(),
        "notices": notices,
        "credits_bytes": credits_path.stat().st_size if credits_path.is_file() else 0,
    }
    if not found["browser_present"]:
        raise FileNotFoundError("bundled_browser_missing")
    if not all(notices.values()) or found["credits_bytes"] < _MIN_CREDITS_BYTES:
        raise FileNotFoundError("browser_notices_missing")
    return found


def _parse_cim_chrome_json(raw: str) -> list[dict[str, Any]]:
    """One CIM JSON document as ``{pid, ppid, exe, cmd}`` rows.

    PowerShell emits an array, one object, ``null``, or nothing. A null path or
    command line becomes an empty string so later checks can count it without
    storing a path in the failure report.
    """
    parsed = json.loads(raw.strip().lstrip("\ufeff") or "[]")
    items = [parsed] if isinstance(parsed, dict) else (parsed or [])
    return [
        {
            "pid": item["ProcessId"],
            "ppid": item["ParentProcessId"],
            "exe": item["ExecutablePath"] or "",
            "cmd": item["CommandLine"] or "",
        }
        for item in items
        if isinstance(item, dict)
    ]


# One process for the whole export. On the Windows Full runner the spawn-plus-query
# interval exceeded a one-shot browser's lifetime. OperationTimeoutSec stops one hung
# CIM call from stalling the loop. AutoFlush pushes each JSON line out before the next query.
_CHROME_WATCH = (
    "$ProgressPreference='SilentlyContinue';"
    "$ErrorActionPreference='SilentlyContinue';"
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;"
    "if ([Console]::Out -is [System.IO.StreamWriter]) { [Console]::Out.AutoFlush = $true };"
    "while ($true) {"
    " $p = @(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" -OperationTimeoutSec 5"
    " | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine);"
    " $json = ConvertTo-Json -InputObject $p -Compress;"
    " if ([string]::IsNullOrEmpty($json)) { $json = '[]' };"
    " [Console]::Out.WriteLine($json);"
    " [Console]::Out.Flush();"
    " Start-Sleep -Milliseconds 100"
    " }"
)


def _windows_sampler() -> bool:
    """True when samples come from :func:`_spawn_chrome_watch` instead of a fresh process each poll.

    Tests replace this. Production follows ``sys.platform`` so a test never has to patch that.
    """
    return sys.platform == "win32"


def _spawn_chrome_watch() -> subprocess.Popen[str]:
    """Start the CIM loop. The caller reads stdout and must terminate the process."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(  # nosec B603 B607 - fixed argv, no user input
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CHROME_WATCH],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=flags,
    )


def _list_processes() -> list[dict[str, Any]]:
    """Every process as ``{pid, ppid, exe, cmd}``; Windows via CIM, else ``ps``.

    The Windows branch is one shot. The export sampler does not use it: a cold
    PowerShell start per sample missed the browser on the Full PNG gate.
    """
    if sys.platform == "win32":
        # Browser processes only (every Chromium child is also chrome.exe), so a sample is quick.
        # InputObject with @() keeps zero or one match a JSON array.
        script = (
            "$p = @(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\""
            " | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine);"
            " ConvertTo-Json -InputObject $p -Compress"
        )
        raw = subprocess.run(  # nosec B603 B607 - fixed argv, no user input
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        ).stdout
        return _parse_cim_chrome_json(raw)
    raw = subprocess.run(  # nosec B603 B607 - fixed argv, no user input
        ["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, check=True, timeout=60
    ).stdout
    rows = []
    for line in raw.splitlines():
        pid, ppid, cmd = line.strip().split(None, 2)
        rows.append({"pid": int(pid), "ppid": int(ppid), "exe": cmd.split(" --", 1)[0], "cmd": cmd})
    return rows


def _descendants(rows: list[dict[str, Any]], root: int) -> list[dict[str, Any]]:
    children: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        children.setdefault(row["ppid"], []).append(row)
    found, stack = [], [root]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child["pid"])
    return found


def _inside(exe: str, base: Path) -> bool:
    """True when *exe* resolves inside *base*, compared case-insensitively where the OS is."""
    import os

    if not exe:
        return False
    target = os.path.normcase(str(Path(exe).resolve()))
    root = os.path.normcase(str(base.resolve()))
    try:
        return os.path.commonpath([target, root]) == root
    except ValueError:  # different drives on Windows
        return False


def _describe_launch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Which browser binaries this process started, relative to the onedir."""
    import os

    base = app_dir().resolve()
    browsers = [row for row in _descendants(rows, os.getpid()) if "chrom" in Path(row["exe"]).name.lower()]
    inside, outside = set(), 0
    flags: set[str] = set()
    for row in browsers:
        if _inside(row["exe"], base):
            relative = os.path.relpath(Path(row["exe"]).resolve(), base)
            inside.add(Path(relative).as_posix())
        else:
            outside += 1
        flags.update(re.findall(r"(?<!\S)(--[a-z0-9-]+)", row["cmd"]))
    return {
        "browser_processes": len(browsers),
        "launched_from_onedir": sorted(inside),
        "launched_outside_onedir": outside,
        "flags": sorted(f for f in flags if f in {"--headless", "--no-sandbox", "--disable-gpu", "--user-data-dir"}),
        "system_chrome_processes_running": sum(
            1 for row in rows if Path(row["exe"]).name.lower() == "chrome.exe" and not _inside(row["exe"], base)
        ),
    }


_SAMPLE_INTERVAL_S = 0.1
_SAMPLER_STOP_TIMEOUT_S = 30.0
_WATCH_READY_TIMEOUT_S = 10.0


def _take_complete_lines(pending: str, piece: str) -> tuple[str, list[str]]:
    """Append *piece* and return ``(remainder, complete lines)``.

    A chunk with no newline stays in the remainder so the caller can keep it
    until the rest of the line arrives.
    """
    text = pending + piece
    if not text.endswith("\n") and not text.endswith("\r"):
        return text, []
    return "", text.splitlines()


def _signal_process(proc: subprocess.Popen[str] | None, *, kill: bool) -> None:
    """End *proc* if it is still running. ``kill`` also waits for it to exit."""
    if proc is None or proc.poll() is not None:
        return
    with contextlib.suppress(OSError):
        if kill:
            proc.kill()
        else:
            proc.terminate()
    if kill:
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)


def _uninspectable_descendants(rows: list[dict[str, Any]]) -> int:
    """Descendants of this process whose executable path is null."""
    import os

    return sum(1 for row in _descendants(rows, os.getpid()) if not row.get("exe"))


class _ProcessSampler:
    """Collect process samples until stopped.

    On Windows one PowerShell process queries CIM in a loop for the whole export.
    Elsewhere each poll is a fresh ``_list_processes`` call. A failed line or probe
    drops that sample and leaves the render running.
    """

    def __init__(self) -> None:
        self.samples: list[list[dict[str, Any]]] = []
        self.did_not_stop = False
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._half_line = threading.Event()
        self._line_done = threading.Event()
        self._proc: subprocess.Popen[str] | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        if self._proc is not None:
            self._read_watch()
            return
        while not self._stop.is_set():
            with contextlib.suppress(Exception):  # a failed probe loses one sample, never the render
                self.samples.append(_list_processes())
            self._stop.wait(_SAMPLE_INTERVAL_S)

    def _read_watch(self) -> None:
        """Record each complete CIM line until stdout hits EOF.

        A fragment with no newline stays buffered, so ``stop`` can avoid cutting it.
        A bad line is skipped and is not logged: the text can contain an executable path.
        """
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        pending = ""
        try:
            for piece in proc.stdout:
                pending, ready = _take_complete_lines(pending, str(piece))
                self._note_pending(pending)
                self._record_lines(ready)
        except Exception:
            return

    def _note_pending(self, pending: str) -> None:
        if pending:
            self._half_line.set()
            return
        self._half_line.clear()
        self._line_done.set()

    def _record_lines(self, lines: list[str]) -> None:
        for line in lines:
            if not line.strip():
                continue
            with contextlib.suppress(Exception):
                self.samples.append(_parse_cim_chrome_json(line))
                self._ready.set()

    def start(self) -> None:
        if _windows_sampler():
            self._proc = _spawn_chrome_watch()
        self._thread.start()

    def wait_until_ready(self, timeout: float) -> bool:
        """True once the watcher has parsed a line, or immediately when there is no watcher."""
        if self._proc is None:
            return True
        return self._ready.wait(timeout)

    def stop(self) -> None:
        """Drain complete lines through EOF, then make sure the reader has exited.

        ``terminate`` runs only when no line fragment is buffered. The kill fallback
        runs after that, and the reader is joined again so a line released by the
        kill is still recorded. A reader that is still alive is flagged, not detached.
        """
        self._stop.set()
        self._wait_out_of_half_line()
        proc = self._proc
        if not self._half_line.is_set():
            _signal_process(proc, kill=False)
        self._join_reader()
        if self._thread.is_alive() or (proc is not None and proc.poll() is None):
            _signal_process(proc, kill=True)
            self._join_reader()
        if self._thread.is_alive():
            self.did_not_stop = True

    def _wait_out_of_half_line(self) -> None:
        if self._half_line.is_set():
            self._line_done.wait(_SAMPLER_STOP_TIMEOUT_S)

    def _join_reader(self) -> None:
        if self._thread.is_alive():  # never started if the payload failed before start()
            self._thread.join(_SAMPLER_STOP_TIMEOUT_S)


def _recording_figure_to_png(real: Any, errors: list[Exception]) -> Any:
    """Wrap *real* so a render error is kept and re-raised.

    The export payload turns a failed image into a notice, so without this the report would
    only say that no PNG was rendered, not why (for example a missing bundled browser).
    """

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return real(*args, **kwargs)
        except Exception as exc:
            errors.append(exc)
            raise

    return wrapped


def _merge_samples(samples: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Union of every sampled process row, keyed by pid and executable."""
    merged: dict[tuple[Any, Any], dict[str, Any]] = {}
    for rows in samples:
        for row in rows:
            merged.setdefault((row["pid"], row["exe"]), row)
    return list(merged.values())


class RenderCheckError(ValueError):
    """The PNGs rendered, but the watched browser did not match the bundle.

    ``code`` is ``browser_not_seen`` when no watched browser was inside the onedir,
    or ``browser_outside`` when one ran outside it. ``counts`` are integers only:
    how many samples were taken, how many rows those samples held, how many of
    those rows had an empty executable, how many descendant browsers were seen,
    how many distinct inside binaries and outside launches that was, and how many
    ``chrome.exe`` rows were outside the onedir. No paths.
    """

    def __init__(self, code: str, **counts: int) -> None:
        super().__init__(code)
        self.code = code
        self.counts = counts


def _launch_counts(launch: dict[str, Any], rows: list[dict[str, Any]], sample_count: int) -> dict[str, int]:
    """Integer totals for a failed launch check. Paths stay out of this dict."""
    return {
        "samples": sample_count,
        "rows": len(rows),
        "empty_exe_rows": sum(1 for row in rows if not row.get("exe")),
        "browser_processes": int(launch["browser_processes"]),
        "launched_inside": len(launch["launched_from_onedir"]),
        "launched_outside": int(launch["launched_outside_onedir"]),
        "system_chrome": int(launch["system_chrome_processes_running"]),
        "uninspectable": _uninspectable_descendants(rows),
    }


def _require_bundled_launch(launch: dict[str, Any], rows: list[dict[str, Any]], sample_count: int) -> None:
    """Pass only when every watched browser has a path inside the onedir.

    A known outside path fails as ``browser_outside``. A descendant with a null
    path fails as ``browser_uninspectable`` because it cannot be placed. No inside
    browser fails as ``browser_not_seen``.
    """
    counts = _launch_counts(launch, rows, sample_count)
    if counts["launched_outside"]:
        raise RenderCheckError("browser_outside", **counts)
    if counts["uninspectable"]:
        raise RenderCheckError("browser_uninspectable", **counts)
    if not launch["launched_from_onedir"]:
        raise RenderCheckError("browser_not_seen", **counts)


def _render_pngs(captured_pages: list[str]) -> dict[str, Any]:
    from kaleido import _page_generator

    from guiskindose import PyskindoseSettings, load_settings_example_json
    from guiskindose.export import collect_export_payload, images
    from guiskindose.main import build_cli_export_source

    original = _page_generator.PageGenerator.generate_index
    original_render = images.figure_to_png
    sampler = _ProcessSampler()
    errors: list[Exception] = []

    def capture(self):  # record exactly the page Kaleido writes to its temp dir
        html = original(self)
        captured_pages.append(html)
        return html

    _page_generator.PageGenerator.generate_index = capture
    images.figure_to_png = _recording_figure_to_png(original_render, errors)
    settings = PyskindoseSettings(settings=load_settings_example_json())
    settings.mode = "calculate_dose"
    settings.phantom.model = "plane"
    started = time.perf_counter()
    try:
        # The watch starts during source load. The payload waits until one line has parsed.
        sampler.start()
        source = build_cli_export_source([str(_pkg("example_data", "RDSR", _EXAMPLE_RDSR))], settings)
        if not sampler.wait_until_ready(_WATCH_READY_TIMEOUT_S):
            raise ValueError("process_sampling_failed")
        payload = collect_export_payload(source, with_images=True)
    finally:
        sampler.stop()
        images.figure_to_png = original_render
        _page_generator.PageGenerator.generate_index = original
    if sampler.did_not_stop:
        raise RenderCheckError("sampler_did_not_stop")
    merged = _merge_samples(sampler.samples)
    launch = _describe_launch(merged)
    pngs = [image.png_bytes for image in payload.images if image.png_bytes]
    result = {
        "images": len(payload.images),
        "png_images": sum(1 for png in pngs if png.startswith(_PNG_MAGIC)),
        "png_bytes_total": sum(len(png) for png in pngs),
        "render_seconds": round(time.perf_counter() - started, 2),
        **launch,
        "samples": len(sampler.samples),
        "rows": len(merged),
    }
    if errors:  # any failed image fails the check; surface the real cause
        raise errors[0]
    if not result["png_images"]:
        raise ValueError("no_png_rendered")
    if not sampler.samples:
        raise ValueError("process_sampling_failed")
    _require_bundled_launch(launch, merged, len(sampler.samples))
    return result


def _check_page(captured_pages: list[str]) -> dict[str, Any]:
    found = {
        "pages_captured": len(captured_pages),
        "http_script_refs": sum(len(_HTTP_SCRIPT.findall(page)) for page in captured_pages),
        "mathjax_referenced": any("mathjax" in page.lower() for page in captured_pages),
    }
    if not captured_pages:
        raise ValueError("kaleido_page_not_captured")
    if found["http_script_refs"]:
        raise ValueError("kaleido_page_references_http_script")
    return found


def run_png_check(output_dir: str, *, process_start: float) -> int:
    """Run the bundled-browser PNG check, write ``pngcheck_report.json``, return the exit code."""
    out_dir = Path(output_dir) / OWNED_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"frozen": bool(getattr(sys, "frozen", False)), "platform": sys.platform}
    pages: list[str] = []
    ok = _run_step(report, "bundle", _check_bundle)
    ok = ok and _run_step(report, "render", lambda: _render_pngs(pages))
    ok = ok and _run_step(report, "page", lambda: _check_page(pages))
    report["passed"] = ok
    report["total_seconds"] = round(time.perf_counter() - process_start, 2)
    _write_atomic(out_dir / "pngcheck_report.json", json.dumps(report, indent=2))
    return 0 if ok else 1
