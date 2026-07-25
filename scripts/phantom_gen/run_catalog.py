#!/usr/bin/env python3
"""Orchestrate catalog → MPFB generate → transform → validate → optional install.

Runs outside Blender (project venv). Invokes ``blender -b -P mpfb_generate.py``
per catalog entry. Affine stretch is used only for anti-balloon controls.

Usage::

    source .venv/bin/activate
    export BLENDER_USER_RESOURCES="$PWD/tmp/blender_user"
    python scripts/phantom_gen/run_catalog.py --only pediatric_5y_male
    python scripts/phantom_gen/run_catalog.py --priority P0
    python scripts/phantom_gen/run_catalog.py --install   # after validate passes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Allow ``python scripts/phantom_gen/run_catalog.py`` without PYTHONPATH=.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.phantom_gen.affine_control import build_affine_control  # noqa: E402
from scripts.phantom_gen.transform_to_psd_frame import (  # noqa: E402
    _load_vertices_faces,
    _write_binary_stl,
    transform_to_psd_frame,
)
from scripts.phantom_gen.validate_phantom import (  # noqa: E402
    abdomen_bulk,
    extents,
    face_up_ok,
    head_ratio,
    load_vertices,
    validate,
)

REPO_ROOT = _REPO_ROOT
DEFAULT_CATALOG = Path(__file__).resolve().parent / "catalog_v1.json"
DEFAULT_OUT = REPO_ROOT / "tmp" / "phantom_gen"
MPFB_GENERATE = Path(__file__).resolve().parent / "mpfb_generate.py"
PHANTOM_DATA = REPO_ROOT / "src" / "mypyskindose" / "phantom_data"

# Catalog ids and Blender basenames are allowlisted before any subprocess argv is built.
_CATALOG_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
_ALLOWED_BLENDER_NAMES = frozenset({"blender", "Blender"})
_MPFB_PROBE_EXPR = (
    "import addon_utils; "
    "ok=any(m.__name__=='bl_ext.blender_org.mpfb' for m in addon_utils.modules()); "
    "print('MPFB_OK' if ok else 'MPFB_MISSING')"
)


def validate_catalog_id(catalog_id: str) -> str:
    """Return ``catalog_id`` only when it matches the allowlisted stem pattern."""
    match = _CATALOG_ID_RE.fullmatch(catalog_id)
    if match is None:
        raise ValueError(f"invalid catalog id: {catalog_id!r}")
    # Rebuild from the match so callers do not retain untrusted CLI taint.
    return match.group(0)


def validate_blender_binary(blender: str) -> Path:
    """Require a resolvable Blender executable with an allowlisted basename."""
    if not blender or any(ch in blender for ch in "\r\n\x00"):
        raise ValueError("invalid blender binary path")
    raw = Path(blender).expanduser()
    if raw.is_file() and os.access(raw, os.X_OK):
        resolved = raw.resolve()
    else:
        found = shutil.which(blender)
        if found is None:
            raise ValueError("blender binary not found")
        resolved = Path(found).resolve()
    if resolved.name not in _ALLOWED_BLENDER_NAMES:
        raise ValueError("unexpected blender binary name")
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError("blender binary is not executable")
    return resolved


def build_blender_probe_argv(blender: Path) -> list[str]:
    """Build Blender probe argv from a validated binary and a fixed Python expr."""
    return [str(blender), "-b", "--python-expr", _MPFB_PROBE_EXPR]


def build_blender_generate_argv(
    blender: Path,
    *,
    catalog_id: str,
    catalog: Path,
    out_dir: Path,
) -> list[str]:
    """Build headless MPFB generate argv from allowlisted / resolved components only."""
    safe_id = validate_catalog_id(catalog_id)
    script = MPFB_GENERATE.resolve()
    if not script.is_file():
        raise FileNotFoundError("mpfb_generate.py missing")
    catalog_path = catalog.expanduser().resolve()
    if not catalog_path.is_file():
        raise FileNotFoundError("catalog JSON missing")
    out_path = out_dir.expanduser().resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    return [
        str(blender),
        "-b",
        "-P",
        str(script),
        "--",
        "--catalog-id",
        safe_id,
        "--catalog",
        str(catalog_path),
        "--out-dir",
        str(out_path),
    ]


def load_catalog(path: Path) -> dict[str, Any]:
    """Load and lightly validate catalog JSON structure."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "entries" not in data or not isinstance(data["entries"], dict):
        raise ValueError("catalog missing entries object")
    for entry_id, entry in data["entries"].items():
        if "base_mesh" in entry or "scale" in entry:
            raise ValueError(
                f"catalog entry {entry_id!r} must not use base_mesh/scale "
                "(affine shipping is forbidden)"
            )
        if "macros" not in entry:
            raise ValueError(f"catalog entry {entry_id!r} missing macros")
        if entry.get("license") != "mpfb-makehuman-assets":
            raise ValueError(f"catalog entry {entry_id!r} missing license mpfb-makehuman-assets")
        if "expect" not in entry:
            raise ValueError(f"catalog entry {entry_id!r} missing expect")
    return data


def resolve_blender(env_local: Path | None = None) -> str:
    """Return Blender executable path from env.local.json, PATH, or common installs."""
    candidates: list[str] = []
    local = env_local or (Path(__file__).resolve().parent / "env.local.json")
    if local.is_file():
        cfg = json.loads(local.read_text(encoding="utf-8"))
        if cfg.get("blender"):
            candidates.append(str(cfg["blender"]))
    env_bin = os.environ.get("BLENDER")
    if env_bin:
        candidates.append(env_bin)
    candidates.extend(
        [
            "blender",
            "/opt/homebrew/bin/blender",
            "/usr/local/bin/blender",
        ]
    )
    for cand in candidates:
        path = Path(cand)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        found = shutil.which(cand)
        if found:
            return found
    raise FileNotFoundError(
        "Blender not found. Install Blender ≥4.2 and/or set scripts/phantom_gen/env.local.json"
    )


def blender_mpfb_available(blender: str | None = None) -> tuple[bool, str]:
    """Return (ok, detail) for headless Blender + MPFB availability."""
    try:
        blender_bin = validate_blender_binary(blender or resolve_blender())
    except (FileNotFoundError, ValueError) as exc:
        return False, str(exc)

    user_resources = os.environ.get("BLENDER_USER_RESOURCES")
    if not user_resources:
        hint = REPO_ROOT / "tmp" / "blender_user"
        if hint.is_dir():
            user_resources = str(hint)

    env = os.environ.copy()
    if user_resources:
        env["BLENDER_USER_RESOURCES"] = user_resources

    # argv rebuilt from validated binary + fixed probe expr (no shell, no CLI taint).
    cmd = build_blender_probe_argv(blender_bin)
    try:
        proc = subprocess.run(  # NOSONAR pythonsecurity:S8705
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"blender_probe_failed:{type(exc).__name__}"

    combined = (proc.stdout or "") + (proc.stderr or "")
    if "MPFB_OK" in combined:
        return True, str(blender_bin)
    if "MPFB_MISSING" in combined:
        return False, "mpfb_not_installed"
    return False, f"blender_probe_exit_{proc.returncode}"


def run_blender_generate(
    *,
    catalog_id: str,
    catalog: Path,
    out_dir: Path,
    blender: str,
) -> Path:
    """Invoke Blender/MPFB generate; return path to OBJ."""
    blender_bin = validate_blender_binary(blender)
    cmd = build_blender_generate_argv(
        blender_bin,
        catalog_id=catalog_id,
        catalog=catalog,
        out_dir=out_dir,
    )
    user_resources = os.environ.get("BLENDER_USER_RESOURCES")
    if not user_resources:
        hint = REPO_ROOT / "tmp" / "blender_user"
        if hint.is_dir():
            user_resources = str(hint)
    env = os.environ.copy()
    if user_resources:
        env["BLENDER_USER_RESOURCES"] = user_resources

    # argv rebuilt from allowlisted id + resolved paths (no shell).
    proc = subprocess.run(  # NOSONAR pythonsecurity:S8705
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        # Avoid dumping absolute paths / full Blender logs into caller stdout by default.
        raise RuntimeError(
            f"mpfb_generate failed for {catalog_id} (exit={proc.returncode}); "
            f"see Blender stderr (length={len(proc.stderr or '')})"
        )
    safe_id = validate_catalog_id(catalog_id)
    obj_path = out_dir.expanduser().resolve() / f"{safe_id}.obj"
    if not obj_path.is_file():
        raise RuntimeError(f"expected OBJ missing for {catalog_id}")
    return obj_path


def transform_obj_to_stl(
    obj_path: Path,
    stl_path: Path,
    *,
    force_flip_y: bool = True,
) -> dict[str, float]:
    """Transform Blender OBJ into PSD-frame STL; return extent summary.

    MPFB exports typically need ``force_flip_y=True`` so the posterior lands at
    max Y (face-up). Per-entry catalog override may set ``force_flip_y`` false
    when a regenerate proves the default is wrong. The asymmetric heuristic is
    often a no-op on these meshes, so the flag is explicit.
    """
    vertices, faces = _load_vertices_faces(obj_path)
    transformed = transform_to_psd_frame(vertices, force_flip_y=force_flip_y)
    _write_binary_stl(stl_path, transformed, faces)
    return extents(transformed)


def check_expect_ranges(ext: dict[str, float], expect: dict[str, Any]) -> list[str]:
    """Return list of expect-range failure messages (empty if ok)."""
    failures: list[str] = []
    for key, span_key in (
        ("height_z", "height_z"),
        ("width_x", "width_x"),
        ("thickness_y", "thickness_y"),
    ):
        bounds = expect.get(key)
        if not bounds or len(bounds) != 2:
            continue
        lo, hi = float(bounds[0]), float(bounds[1])
        value = float(ext[span_key])
        if value < lo or value > hi:
            failures.append(f"{key}={value:.2f} outside [{lo}, {hi}]")
    return failures


def resolve_affine_ref_id(catalog: dict[str, Any], entry: dict[str, Any]) -> str:
    """Pick MPFB shape-ref catalog id (female ref when gender macro < 0.5)."""
    cfg = catalog.get("affine_control_base")
    if not isinstance(cfg, dict) or cfg.get("method") != "mpfb_catalog_id":
        raise ValueError("affine_control_base must use method mpfb_catalog_id")
    gender = float(entry.get("macros", {}).get("gender", 1.0))
    if gender < 0.5 and cfg.get("id_female"):
        return str(cfg["id_female"])
    return str(cfg["id"])


def ensure_affine_control_base(
    catalog: dict[str, Any],
    *,
    catalog_path: Path,
    out_dir: Path,
    blender: str,
    entry: dict[str, Any] | None = None,
) -> Path:
    """Return STL path for affine-control base (generate MPFB ref if configured)."""
    cfg = catalog.get("affine_control_base", "src/mypyskindose/phantom_data/adult_male.stl")
    if isinstance(cfg, str):
        path = REPO_ROOT / cfg
        if not path.is_file():
            raise FileNotFoundError(f"affine_control_base missing: {cfg}")
        return path

    method = cfg.get("method")
    if method != "mpfb_catalog_id":
        raise ValueError(f"unsupported affine_control_base method: {method!r}")
    ref_id = resolve_affine_ref_id(catalog, entry or {})
    if ref_id not in catalog["entries"]:
        raise KeyError(f"affine_control_base catalog id missing: {ref_id}")

    ref_stl = out_dir / f"{ref_id}.stl"
    if ref_stl.is_file():
        return ref_stl

    # Generate reference without recursive shape compare.
    obj_path = run_blender_generate(
        catalog_id=ref_id,
        catalog=catalog_path,
        out_dir=out_dir,
        blender=blender,
    )
    transform_obj_to_stl(obj_path, ref_stl)
    return ref_stl


def process_entry(
    catalog_id: str,
    catalog: dict[str, Any],
    *,
    catalog_path: Path,
    out_dir: Path,
    blender: str,
    skip_phantom_load: bool = False,
    skip_shape: bool = False,
) -> dict[str, Any]:
    """Generate → transform → validate one catalog entry."""
    entry = catalog["entries"][catalog_id]
    expect = entry["expect"]
    report: dict[str, Any] = {"id": catalog_id, "passed": False, "steps": {}}

    obj_path = run_blender_generate(
        catalog_id=catalog_id,
        catalog=catalog_path,
        out_dir=out_dir,
        blender=blender,
    )
    report["steps"]["generate"] = {"ok": True, "obj": str(obj_path.name)}

    stl_path = out_dir / f"{catalog_id}.stl"
    force_flip = bool(entry.get("force_flip_y", True))
    ext = transform_obj_to_stl(obj_path, stl_path, force_flip_y=force_flip)
    report["steps"]["transform"] = {"ok": True, "extents": ext, "force_flip_y": force_flip}

    # Clinical face-up gate (same PSD convention as fun demos).
    fu_pass, fu_detail = face_up_ok(load_vertices(stl_path))
    report["steps"]["face_up"] = {"ok": fu_pass, **fu_detail}
    if not fu_pass:
        report["passed"] = False
        report["stl"] = str(stl_path)
        return report

    range_failures = check_expect_ranges(ext, expect)
    report["steps"]["expect_ranges"] = {"ok": not range_failures, "failures": range_failures}

    compare_affine: Path | None = None
    metric = expect.get("shape_metric")
    margin = float(expect.get("shape_margin", 0.05))
    if not skip_shape and metric:
        base_stl = ensure_affine_control_base(
            catalog,
            catalog_path=catalog_path,
            out_dir=out_dir,
            blender=blender,
            entry=entry,
        )
        control_stl = out_dir / f"control_{catalog_id}.stl"
        build_affine_control(base_stl, stl_path, control_stl, mode="uniform_height")
        compare_affine = control_stl
        report["steps"]["affine_control"] = {
            "ok": True,
            "control": control_stl.name,
            "base": base_stl.name,
        }

    validation = validate(
        stl_path,
        compare_affine=compare_affine,
        metric=metric if compare_affine is not None else None,
        metric_margin=margin,
        skip_phantom_load=skip_phantom_load,
    )
    report["steps"]["validate"] = validation

    # Absolute head_ratio floor for pediatrics (in addition to vs-control).
    head_min = expect.get("head_ratio_min")
    if head_min is not None:
        verts = load_vertices(stl_path)
        hr = head_ratio(verts)
        ok_hr = hr >= float(head_min)
        report["steps"]["head_ratio_min"] = {"value": hr, "min": head_min, "ok": ok_hr}
    else:
        ok_hr = True

    report["passed"] = bool(not range_failures and validation.get("passed") and ok_hr)
    report["stl"] = str(stl_path)
    report["abdomen_bulk"] = abdomen_bulk(load_vertices(stl_path)) if stl_path.is_file() else None
    return report


def install_stl(stl_path: Path, catalog_id: str) -> Path:
    """Copy validated STL into phantom_data (does not write privacy inventory)."""
    PHANTOM_DATA.mkdir(parents=True, exist_ok=True)
    dest = PHANTOM_DATA / f"{catalog_id}.stl"
    shutil.copy2(stl_path, dest)
    return dest


def select_ids(
    catalog: dict[str, Any],
    *,
    only: str | None,
    priority: str | None,
) -> list[str]:
    """Resolve which catalog ids to process (skips REF / ship:false unless --only)."""
    entries = catalog["entries"]
    if only:
        if only not in entries:
            raise KeyError(f"unknown catalog id: {only}")
        return [only]
    ids = [
        i
        for i, e in entries.items()
        if e.get("priority") != "REF" and e.get("ship", True) is not False
    ]
    if priority:
        ids = [i for i in ids if entries[i].get("priority") == priority]
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", type=str, default=None, help="Single catalog id")
    parser.add_argument("--priority", choices=["P0", "P1"], default=None)
    parser.add_argument("--install", action="store_true", help="Copy passing STLs to phantom_data/")
    parser.add_argument("--skip-phantom-load", action="store_true")
    parser.add_argument("--skip-shape", action="store_true", help="Skip affine anti-balloon checks")
    parser.add_argument("--json-report", type=Path, default=None)
    parser.add_argument("--blender", type=str, default=None)
    args = parser.parse_args(argv)

    catalog = load_catalog(args.catalog)
    try:
        ids = select_ids(catalog, only=args.only, priority=args.priority)
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not ids:
        print("ERROR: no catalog ids selected", file=sys.stderr)
        return 2

    try:
        blender = validate_blender_binary(args.blender or resolve_blender())
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    ok_mpfb, detail = blender_mpfb_available(str(blender))
    if not ok_mpfb:
        print(f"ERROR: Blender/MPFB unavailable ({detail})", file=sys.stderr)
        return 2

    reports: list[dict[str, Any]] = []
    failures = 0
    for catalog_id in ids:
        print(f"=== {catalog_id} ===")
        try:
            report = process_entry(
                catalog_id,
                catalog,
                catalog_path=args.catalog,
                out_dir=args.out_dir,
                blender=str(blender),
                skip_phantom_load=args.skip_phantom_load,
                skip_shape=args.skip_shape,
            )
        except Exception as exc:  # noqa: BLE001 — surface per-id failure, continue others
            report = {
                "id": catalog_id,
                "passed": False,
                "error": f"{type(exc).__name__}:{exc}",
            }
            print(f"FAIL {catalog_id}: {report['error']}")
            failures += 1
            reports.append(report)
            continue

        status = "PASS" if report["passed"] else "FAIL"
        print(f"{status} {catalog_id}")
        if not report["passed"]:
            failures += 1
            if report["steps"].get("expect_ranges", {}).get("failures"):
                print(f"  expect: {report['steps']['expect_ranges']['failures']}")
            if not report["steps"].get("validate", {}).get("passed"):
                print(f"  validate checks: {report['steps']['validate'].get('checks')}")

        if args.install and report["passed"]:
            entry = catalog["entries"][catalog_id]
            if entry.get("ship", True) is False or entry.get("priority") == "REF":
                print(f"  skip install (non-shipped ref): {catalog_id}")
            else:
                dest = install_stl(Path(report["stl"]), catalog_id)
                report["installed"] = dest.name
                print(f"  installed → phantom_data/{dest.name}")

        reports.append(report)

    summary = {"passed": failures == 0, "n_fail": failures, "reports": reports}
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"=== done: {len(ids) - failures}/{len(ids)} passed ===")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
