"""Offline PNG check for a Full-shape frozen GUISkinDose build.

Run as ``GUISkinDose.exe --png-check <output dir>``. It renders the dose-map PNGs of
the bundled example RDSR through Kaleido, using only the Chromium copied into the
onedir under ``chromium/``. Its path is passed to ``kaleido.start_sync_server``
explicitly, because choreographer would otherwise prefer a Chrome for Testing it
downloaded earlier, then ``BROWSER_PATH``, then a system install.

It fails unless:

- the bundled browser and its license notices are present,
- at least one PNG comes back,
- every browser process launched under this process runs from inside the onedir,
- the page Kaleido generated references no ``http(s)`` script URL.

The report ``pngcheck_report.json`` holds booleans, counts, flag names, and paths
relative to the onedir only: no absolute paths and no exam values.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess  # nosec B404 - fixed argv, used only to list this process's children
import sys
import time
from pathlib import Path
from typing import Any

from selfcheck import _EXAMPLE_RDSR, OWNED_SUBDIR, _pkg, _run_step, _write_atomic

BROWSER_DIR = "chromium"
# Notices that must sit beside the bundled browser (PORTABLE_CHROMIUM_ARTIFACT.md).
NOTICE_FILES = ("LICENSE.chromium.txt", "LICENSE.ungoogled-chromium-windows.txt", "CREDITS.html")
_MIN_CREDITS_BYTES = 100_000
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_HTTP_SCRIPT = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']?\s*https?:", re.IGNORECASE)
_logger = logging.getLogger("guiskindose.portable.pngcheck")


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent


def bundled_browser() -> Path:
    name = "chrome.exe" if sys.platform == "win32" else "chrome"
    return app_dir() / BROWSER_DIR / name


def _check_bundle() -> dict[str, Any]:
    browser = bundled_browser()
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


def _list_processes() -> list[dict[str, Any]]:
    """Every process as ``{pid, ppid, exe, cmd}``; Windows via CIM, else ``ps``."""
    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine"
            " | ConvertTo-Json -Compress"
        )
        raw = subprocess.run(  # nosec B603 B607 - fixed argv, no user input
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        ).stdout
        return [
            {
                "pid": p["ProcessId"],
                "ppid": p["ParentProcessId"],
                "exe": p["ExecutablePath"] or "",
                "cmd": p["CommandLine"] or "",
            }
            for p in json.loads(raw)
        ]
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


def _describe_launch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Which browser binaries this process started, relative to the onedir."""
    import os

    base = app_dir()
    browsers = [row for row in _descendants(rows, os.getpid()) if "chrom" in Path(row["exe"]).name.lower()]
    inside, outside = set(), 0
    flags: set[str] = set()
    for row in browsers:
        exe = Path(row["exe"]).resolve()
        if exe.is_relative_to(base):
            inside.add(exe.relative_to(base).as_posix())
        else:
            outside += 1
        flags.update(re.findall(r"(?<!\S)(--[a-z0-9-]+)", row["cmd"]))
    return {
        "browser_processes": len(browsers),
        "launched_from_onedir": sorted(inside),
        "launched_outside_onedir": outside,
        "flags": sorted(f for f in flags if f in {"--headless", "--no-sandbox", "--disable-gpu", "--user-data-dir"}),
        "system_chrome_processes_running": sum(
            1 for row in rows if Path(row["exe"]).name.lower() == "chrome.exe" and not row["exe"].startswith(str(base))
        ),
    }


def _render_pngs(captured_pages: list[str]) -> dict[str, Any]:
    import kaleido
    from kaleido import _page_generator

    from guiskindose import PyskindoseSettings, load_settings_example_json
    from guiskindose.export import collect_export_payload
    from guiskindose.main import build_cli_export_source

    original = _page_generator.PageGenerator.generate_index

    def capture(self):  # record exactly the page Kaleido writes to its temp dir
        html = original(self)
        captured_pages.append(html)
        return html

    _page_generator.PageGenerator.generate_index = capture
    settings = PyskindoseSettings(settings=load_settings_example_json())
    settings.mode = "calculate_dose"
    settings.phantom.model = "plane"
    started = time.perf_counter()
    kaleido.start_sync_server(path=str(bundled_browser()), mathjax=False, silence_warnings=True)
    try:
        source = build_cli_export_source([str(_pkg("example_data", "RDSR", _EXAMPLE_RDSR))], settings)
        payload = collect_export_payload(source, with_images=True)
        launch = _describe_launch(_list_processes())
    finally:
        kaleido.stop_sync_server(silence_warnings=True)
        _page_generator.PageGenerator.generate_index = original
    pngs = [image.png_bytes for image in payload.images if image.png_bytes]
    result = {
        "images": len(payload.images),
        "png_images": sum(1 for png in pngs if png.startswith(_PNG_MAGIC)),
        "png_bytes_total": sum(len(png) for png in pngs),
        "render_seconds": round(time.perf_counter() - started, 2),
        **launch,
    }
    if not result["png_images"]:
        raise ValueError("no_png_rendered")
    if not launch["launched_from_onedir"] or launch["launched_outside_onedir"]:
        raise ValueError("browser_not_bundled_copy")
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
    ok = _run_step(report, "page", lambda: _check_page(pages)) and ok
    report["passed"] = ok
    report["total_seconds"] = round(time.perf_counter() - process_start, 2)
    _write_atomic(out_dir / "pngcheck_report.json", json.dumps(report, indent=2))
    return 0 if ok else 1
