"""Headless self-check for a frozen GUISkinDose build.

Run as ``GUISkinDose.exe --self-check <output dir>``. It proves, from inside the
freeze, that every packaged data root resolves through the installed package,
that the GUI and native-window libraries import, and that a plane-phantom
``calculate_dose`` on a bundled example RDSR exports HTML, JSON, and CSV. It
needs no network and no ``git``.

The result is ``selfcheck_report.json`` in the output directory, plus the exit
code (0 = every check passed). The report holds counts, booleans, and package
relative names only: no absolute paths and no exam values beyond the PSD of a
synthetic bundled example.
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import logging
import math
import shutil
import sys
import time
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

_EXAMPLE_RDSR = "siemens_axiom_example_procedure.dcm"
_logger = logging.getLogger("guiskindose.portable.selfcheck")


def _pkg(*parts: str):
    node = files("guiskindose")
    for part in parts:
        node = node / part
    return node


def _count(parts: tuple[str, ...], suffix: str) -> int:
    return sum(1 for item in _pkg(*parts).iterdir() if item.name.endswith(suffix))


def _read_json(*parts: str) -> int:
    return len(json.loads(_pkg(*parts).read_text(encoding="utf-8")))


def _check_package_data() -> dict[str, Any]:
    """Open every data root the portable plan lists, through ``importlib.resources``."""
    from guiskindose.gui.ui_copy import _PACKAGED_CATALOG_TRAVERSABLE, _load_catalog
    from guiskindose.phantom_mesh_names import resolve_human_mesh_stl_path

    kerma_csv = _pkg("example_data", "kerma_meter", "calibration_factors_example.csv")
    return {
        "phantom_data_stl": _count(("phantom_data",), ".stl"),
        "hudfrid_stl_bytes": resolve_human_mesh_stl_path("hudfrid").stat().st_size,
        "table_data_csv": _count(("table_data",), ".csv"),
        "hvl_tables_csv": _count(("table_data", "hvl_tables"), ".csv"),
        "gui_help_md": _count(("gui", "help"), ".md"),
        "gui_static_icons": _count(("gui", "static"), ".ico") + _count(("gui", "static"), ".svg"),
        "gui_static_fonts": _count(("gui", "static", "fonts"), ".woff2"),
        "ui_copy_packaged": _PACKAGED_CATALOG_TRAVERSABLE.is_file(),
        "ui_copy_keys": len(_load_catalog()),
        "normalization_settings_keys": _read_json("normalization_settings.json"),
        "settings_example_keys": _read_json("settings_example.json"),
        "kerma_example_rows": len(kerma_csv.read_text(encoding="utf-8").splitlines()),
        "example_rdsr_dcm": _count(("example_data", "RDSR"), ".dcm"),
        "example_tabular_csv": _count(("example_data", "tabular"), ".csv"),
    }


def _check_imports() -> dict[str, Any]:
    """Import the GUI stack the window needs; pywebview only where it is the window."""
    modules = ["nicegui", "guiskindose.gui.app", "plotly", "kaleido", "reportlab", "docx", "openpyxl"]
    if not sys.platform.startswith("linux"):
        modules.append("webview")
    result: dict[str, Any] = {}
    for name in modules:
        try:
            importlib.import_module(name)
            result[name] = True
        except ImportError as exc:
            result[name] = f"missing:{exc.name}"
    missing = [name for name, value in result.items() if value is not True]
    if missing:
        raise ImportError(f"modules_missing:{','.join(missing)}")
    return result


def _calculate_and_export(out_dir: Path) -> dict[str, Any]:
    """Plane-phantom calculate_dose on a bundled RDSR; write HTML, JSON, and CSV."""
    from guiskindose import PyskindoseSettings, load_settings_example_json
    from guiskindose.export import collect_export_payload
    from guiskindose.export.writers import write_report
    from guiskindose.main import build_cli_export_source, main
    from guiskindose.safe_output import atomic_write_private

    rdsr = str(_pkg("example_data", "RDSR", _EXAMPLE_RDSR))
    settings = PyskindoseSettings(settings=load_settings_example_json())
    settings.mode = "calculate_dose"
    settings.phantom.model = "plane"

    started = time.perf_counter()
    source = build_cli_export_source([rdsr], settings, report_title="Portable self-check")
    payload = collect_export_payload(source, with_images=False)
    write_report(payload, out_dir / "selfcheck.html", "html", allow_ignored_checkout=True)

    settings.output_format = "json"
    result_json = main(file_path=rdsr, settings=settings)
    if not isinstance(result_json, str):
        raise TypeError("json_output_not_text")
    atomic_write_private(out_dir / "selfcheck.json", result_json.encode("utf-8"), allow_ignored_checkout=True)
    result = json.loads(result_json)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["cell", "dose_mGy"])
    writer.writerows(enumerate(result["dose_map"]))
    atomic_write_private(
        out_dir / "selfcheck_dose_map.csv", buffer.getvalue().encode("utf-8"), allow_ignored_checkout=True
    )

    psd = float(result["psd"])
    if not math.isfinite(psd) or psd <= 0:
        raise ValueError("psd_not_positive")
    return {
        "psd_mGy": round(psd, 4),
        "dose_map_cells": len(result["dose_map"]),
        "calc_and_export_seconds": round(time.perf_counter() - started, 2),
        "html_bytes": (out_dir / "selfcheck.html").stat().st_size,
        "json_bytes": (out_dir / "selfcheck.json").stat().st_size,
        "csv_bytes": (out_dir / "selfcheck_dose_map.csv").stat().st_size,
    }


def _log_sink_state() -> dict[str, Any]:
    from guiskindose.debug import default_native_log_path

    path = default_native_log_path()
    return {"log_file_created": bool(path is not None and path.is_file())}


def _run_step(report: dict[str, Any], name: str, step: Callable[[], dict[str, Any]]) -> bool:
    try:
        report[name] = step()
        return True
    except Exception as exc:  # every step failure is reported, not raised
        from guiskindose.privacy import exception_class_name, innermost_location, safe_error_event

        safe_error_event(_logger, f"selfcheck_{name}", exc)
        report[name] = {"error_type": exception_class_name(exc), "at": innermost_location(exc)}
        return False


def run_self_check(output_dir: str, *, process_start: float) -> int:
    """Run every check, write ``selfcheck_report.json``, and return the exit code."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "git_on_path": shutil.which("git") is not None,
        "stdout_was_none": type(sys.stdout).__name__ == "_LogStream",
    }
    ok = _run_step(report, "package_data", _check_package_data)
    ok = _run_step(report, "imports", _check_imports) and ok
    ok = _run_step(report, "calculate_export", lambda: _calculate_and_export(out_dir)) and ok
    ok = _run_step(report, "log_sink", _log_sink_state) and ok
    report["passed"] = ok
    report["total_seconds"] = round(time.perf_counter() - process_start, 2)
    (out_dir / "selfcheck_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if ok else 1
