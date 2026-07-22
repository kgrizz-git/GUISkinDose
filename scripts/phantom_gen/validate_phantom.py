#!/usr/bin/env python3
"""Validate a phantom STL against MyPySkinDose frame + optional shape metrics.

Usage::

    python scripts/phantom_gen/validate_phantom.py path.stl
    python scripts/phantom_gen/validate_phantom.py path.stl --compare-affine control.stl --metric head_ratio
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def load_vertices(path: Path) -> np.ndarray:
    from stl import mesh as stl_mesh

    m = stl_mesh.Mesh.from_file(str(path))
    return m.vectors.reshape(-1, 3).astype(float)


def face_count(path: Path) -> int:
    from stl import mesh as stl_mesh

    m = stl_mesh.Mesh.from_file(str(path))
    return int(len(m.vectors))


def extents(vertices: np.ndarray) -> dict[str, float]:
    mins = vertices.min(axis=0)
    maxs = vertices.max(axis=0)
    return {
        "x_min": float(mins[0]),
        "x_max": float(maxs[0]),
        "y_min": float(mins[1]),
        "y_max": float(maxs[1]),
        "z_min": float(mins[2]),
        "z_max": float(maxs[2]),
        "width_x": float(maxs[0] - mins[0]),
        "thickness_y": float(maxs[1] - mins[1]),
        "height_z": float(maxs[2] - mins[2]),
        "x_mid": float(0.5 * (mins[0] + maxs[0])),
    }


def _band_mean_radial(vertices: np.ndarray, z_hi_frac: float, z_lo_frac: float) -> float:
    """Mean radial extent in a Z band defined as fractions down from head (z_max)."""
    z = vertices[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    height = z_max - z_min
    if height <= 0:
        return 0.0
    z_hi = z_max - z_hi_frac * height
    z_lo = z_max - z_lo_frac * height
    band = vertices[(z <= z_hi) & (z >= z_lo)]
    if len(band) < 10:
        return 0.0
    x_mid = 0.5 * (float(band[:, 0].min()) + float(band[:, 0].max()))
    y_mid = 0.5 * (float(band[:, 1].min()) + float(band[:, 1].max()))
    radial = np.sqrt((band[:, 0] - x_mid) ** 2 + (band[:, 1] - y_mid) ** 2)
    return float(np.mean(radial))


def head_ratio(vertices: np.ndarray) -> float:
    """Head bulk / torso bulk: superior 0–12% vs mid-torso 25–45% mean radial extent."""
    head = _band_mean_radial(vertices, 0.0, 0.12)
    torso = _band_mean_radial(vertices, 0.25, 0.45)
    if torso <= 1e-9:
        return 0.0
    return head / torso


def abdomen_bulk(vertices: np.ndarray) -> float:
    """Mean radial extent in a mid-torso Z band."""
    return _band_mean_radial(vertices, 0.15, 0.45)


def is_watertight(path: Path) -> bool | None:
    try:
        import trimesh
    except ImportError:
        return None
    mesh = trimesh.load(str(path), force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    return bool(mesh.is_watertight)


def phantom_load_ok(path: Path, name: str) -> tuple[bool, str]:
    try:
        from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
    except Exception as exc:  # noqa: BLE001
        return False, f"import_failed:{type(exc).__name__}"
    try:
        settings = PyskindoseSettings(load_settings_example_json())
        phantom = Phantom(
            phantom_model="human",
            phantom_dim=settings.phantom.dimension,
            human_mesh=(name, path),
        )
        if len(phantom.r) == 0 or len(phantom.n) == 0:
            return False, "empty_geometry"
        return True, f"verts={len(phantom.r)}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}:{exc}"


def validate(
    stl_path: Path,
    *,
    compare_affine: Path | None = None,
    metric: str | None = None,
    metric_margin: float = 0.05,
    skip_phantom_load: bool = False,
) -> dict:
    results: dict = {"file": str(stl_path), "passed": False, "checks": {}}
    if not stl_path.exists():
        results["checks"]["exists"] = False
        return results
    results["checks"]["exists"] = True

    faces = face_count(stl_path)
    results["checks"]["face_count"] = faces
    results["checks"]["face_count_ok"] = 1000 <= faces <= 40000

    verts = load_vertices(stl_path)
    ext = extents(verts)
    results["checks"]["extents"] = ext
    results["checks"]["anchors_ok"] = (
        abs(ext["y_max"]) < 1.0 and abs(ext["z_max"]) < 1.0 and abs(ext["x_mid"]) < 1.0
    )
    results["checks"]["scale_ok"] = 50.0 < ext["height_z"] < 220.0

    wt = is_watertight(stl_path)
    results["checks"]["watertight"] = wt
    results["checks"]["watertight_ok"] = wt is True or wt is None

    results["checks"]["head_ratio"] = head_ratio(verts)
    results["checks"]["abdomen_bulk"] = abdomen_bulk(verts)

    if not skip_phantom_load:
        ok, detail = phantom_load_ok(stl_path, stl_path.stem)
        results["checks"]["phantom_load_ok"] = ok
        results["checks"]["phantom_load_detail"] = detail
    else:
        results["checks"]["phantom_load_ok"] = True
        results["checks"]["phantom_load_detail"] = "skipped"

    shape_ok = True
    if compare_affine is not None and metric:
        c_verts = load_vertices(compare_affine)
        if metric == "head_ratio":
            a = results["checks"]["head_ratio"]
            b = head_ratio(c_verts)
            shape_ok = a > b * (1.0 + metric_margin)
            results["checks"]["shape_compare"] = {
                "metric": metric,
                "candidate": a,
                "affine_control": b,
                "required_margin": metric_margin,
                "passed": shape_ok,
            }
        elif metric == "abdomen_bulk":
            a = results["checks"]["abdomen_bulk"]
            b = abdomen_bulk(c_verts)
            shape_ok = a > b * (1.0 + metric_margin)
            results["checks"]["shape_compare"] = {
                "metric": metric,
                "candidate": a,
                "affine_control": b,
                "required_margin": metric_margin,
                "passed": shape_ok,
            }
        else:
            results["checks"]["shape_compare"] = {"error": f"unknown metric {metric}"}
            shape_ok = False

    results["passed"] = bool(
        results["checks"]["face_count_ok"]
        and results["checks"]["anchors_ok"]
        and results["checks"]["scale_ok"]
        and results["checks"]["watertight_ok"]
        and results["checks"]["phantom_load_ok"]
        and shape_ok
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path)
    parser.add_argument("--compare-affine", type=Path, default=None)
    parser.add_argument("--metric", choices=["head_ratio", "abdomen_bulk"], default=None)
    parser.add_argument("--metric-margin", type=float, default=0.05)
    parser.add_argument("--skip-phantom-load", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = validate(
        args.stl,
        compare_affine=args.compare_affine,
        metric=args.metric,
        metric_margin=args.metric_margin,
        skip_phantom_load=args.skip_phantom_load,
    )
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("=== Phantom validation ===")
        print(f"file: {results['file']}")
        for key, value in results["checks"].items():
            print(f"  {key}: {value}")
        print(f"passed: {results['passed']}")
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
