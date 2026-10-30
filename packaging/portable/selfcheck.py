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
import os
import shutil
import sys
import time
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

_EXAMPLE_RDSR = "siemens_axiom_example_procedure.dcm"
# Plane-phantom PSD for _EXAMPLE_RDSR with settings_example.json, from unfrozen runs on
# macOS and Windows (2026-10-30). A freeze that drops or swaps a correction table moves it.
GOLDEN_PSD_MGY = 8.9542
_GOLDEN_REL_TOL = 1e-3
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
    found = {
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
        "equipment_profile_json": _count(("example_data", "equipment_profiles"), ".json"),
        "equipment_profile_csv": _count(("example_data", "equipment_profiles"), ".csv"),
        "equipment_profile_readme": _pkg("example_data", "equipment_profiles", "README.md").is_file(),
    }
    empty = [name for name, value in found.items() if not value]
    if empty:
        raise FileNotFoundError(f"package_data_missing:{','.join(empty)}")
    return found


def _check_metadata() -> dict[str, Any]:
    """Distribution metadata the app reads at runtime (``__version__``, library versions)."""
    from importlib.metadata import version

    import guiskindose

    found: dict[str, Any] = {"guiskindose_version": guiskindose.__version__}
    for dist in ("nicegui", "plotly"):
        found[f"{dist}_version"] = version(dist)
    if guiskindose.__version__ == "0.0.0+unknown":
        raise LookupError("guiskindose_metadata_missing")
    return found


def _check_repo_root_climbs() -> dict[str, Any]:
    """Exercise the two ``parents[3]`` lookups that assume a source checkout.

    In a bundle they point outside the app, so the code must fall back cleanly: the
    UI copy comes from the packaged catalog, and mesh measurement works without the
    fun-mesh manifest.
    """
    from guiskindose.gui import helpers, ui_copy

    width = helpers.get_mesh_baseline_torso_width("hudfrid")
    found = {
        "ui_copy_read_from_package": ui_copy._read_catalog_text()
        == ui_copy._PACKAGED_CATALOG_TRAVERSABLE.read_text(encoding="utf-8"),
        "fun_mesh_manifest_present": helpers._FUN_MESH_MANIFEST_PATH.is_file(),
        "fun_manifest_override": helpers._fun_manifest_torso_override("hudfrid") != (None, None),
        "hudfrid_torso_width_cm": round(width, 2),
    }
    if not found["ui_copy_read_from_package"] or width <= 0:
        raise ValueError("repo_root_fallback_failed")
    return found


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
    if not math.isclose(psd, GOLDEN_PSD_MGY, rel_tol=_GOLDEN_REL_TOL):
        raise ValueError("psd_differs_from_golden")
    return {
        "psd_mGy": round(psd, 4),
        "golden_psd_mGy": GOLDEN_PSD_MGY,
        "dose_map_cells": len(result["dose_map"]),
        "calc_and_export_seconds": round(time.perf_counter() - started, 2),
        "html_bytes": (out_dir / "selfcheck.html").stat().st_size,
        "json_bytes": (out_dir / "selfcheck.json").stat().st_size,
        "csv_bytes": (out_dir / "selfcheck_dose_map.csv").stat().st_size,
    }


def _log_sink_state() -> dict[str, Any]:
    from guiskindose.debug import default_native_log_path

    if os.environ.get("GUISKINDOSE_NO_FILE_LOG"):
        return {"log_file_created": False, "opted_out": True}
    path = default_native_log_path()
    if path is None or not path.is_file():
        raise FileNotFoundError("diagnostic_log_missing")
    return {"log_file_created": True}


def _write_atomic(path: Path, text: str) -> None:
    """Write *text* to a sibling temp file, then replace *path* in one step.

    CI reads the report as soon as the process exits; a partial file must never
    look like a result.
    """
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


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
    ok = _run_step(report, "metadata", _check_metadata) and ok
    ok = _run_step(report, "imports", _check_imports) and ok
    ok = _run_step(report, "repo_root_climbs", _check_repo_root_climbs) and ok
    ok = _run_step(report, "calculate_export", lambda: _calculate_and_export(out_dir)) and ok
    ok = _run_step(report, "log_sink", _log_sink_state) and ok
    report["passed"] = ok
    report["total_seconds"] = round(time.perf_counter() - process_start, 2)
    _write_atomic(out_dir / "selfcheck_report.json", json.dumps(report, indent=2))
    return 0 if ok else 1


# A fixed public HTTPS endpoint. The request carries no data; CI expects it to fail.
_PROBE_URL = "https://pypi.org/simple/"


def run_network_probe(output_dir: str) -> int:
    """Try one outbound HTTPS request and record whether it was blocked.

    Used by the spike workflow to prove its firewall rule applies to the frozen exe.
    Writes ``network_probe.json`` holding a boolean and an exception class name only.
    """
    import urllib.error
    import urllib.request

    from guiskindose.privacy import exception_class_name

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"outbound_blocked": False, "error_type": None}
    try:
        with urllib.request.urlopen(_PROBE_URL, timeout=15):  # nosec B310 - fixed https URL
            pass
    except urllib.error.HTTPError as exc:
        # The server answered, so the request left the machine: not blocked.
        result = {"outbound_blocked": False, "error_type": exception_class_name(exc)}
    except OSError as exc:
        result = {"outbound_blocked": True, "error_type": exception_class_name(exc)}
    _write_atomic(out_dir / "network_probe.json", json.dumps(result))
    return 0
