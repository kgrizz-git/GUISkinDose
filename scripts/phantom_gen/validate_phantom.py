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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.phantom_gen.path_safety import resolve_under_roots  # noqa: E402

# Shared einsum subscripts for Moller-Trumbore pairwise dots (python:S1192).
_EINSUM_PAIRWISE_DOT = "ij,ij->i"


def load_vertices(path: Path) -> np.ndarray:
    from stl import mesh as stl_mesh

    safe = resolve_under_roots(path, must_be_file=True)
    m = stl_mesh.Mesh.from_file(str(safe))  # NOSONAR pythonsecurity:S2083
    return m.vectors.reshape(-1, 3).astype(float)


def face_count(path: Path) -> int:
    from stl import mesh as stl_mesh

    safe = resolve_under_roots(path, must_be_file=True)
    m = stl_mesh.Mesh.from_file(str(safe))  # NOSONAR pythonsecurity:S2083
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
    safe = resolve_under_roots(path, must_be_file=True)
    mesh = trimesh.load(str(safe), force="mesh")  # NOSONAR pythonsecurity:S2083
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    return bool(mesh.is_watertight)


# --- Fun / demo (non-clinical) ingest gates -----------------------------------
#
# These gates support the demo-phantom ingest pipeline (Cosmic Buddha, Petite
# Herculanaise, Ramesses II, Steamboat Willie). See
# ``dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md``. They enforce a
# face-up supine orientation and outward-facing surface normals, which the
# clinical validator does not check. Statue/cartoon bounding boxes are often
# near-symmetric in Y, so the ``flip_y_if_needed`` heuristic can silently leave
# a mesh face-down; these gates catch that before shipping.

# Default clinical validator ceiling (kept for backwards compatibility).
CLINICAL_MAX_FACES = 40000
# Fun / demo shipping ceiling (hard cap enforced when ``--require-trimesh``).
FUN_MAX_FACES = 20000
# Minimum sampled ray hits before the outward-normal gate is meaningful.
_MIN_NORMAL_SAMPLES = 8


def face_up_ok(
    vertices: np.ndarray,
    *,
    face_up_frac: float = 0.55,
    band_frac: float = 0.12,
) -> tuple[bool, dict]:
    """Check that the anterior (chest/face) lies toward -Y in the superior band.

    In the PSD frame the posterior/back rests on the table at ``y_max ~= 0`` and
    the anterior points toward ``-Y``. For a face-up supine mesh, the superior
    ``band_frac`` Z band (measured from ``z_max`` toward the feet) must reach a
    long way toward ``-Y``. Concretely we require::

        y_min_headband <= y_max - face_up_frac * thickness_y

    where ``thickness_y`` is the full anterior-posterior extent of the mesh.

    Parameters
    ----------
    vertices:
        ``(N, 3)`` vertex array already in the PSD frame (cm).
    face_up_frac:
        Fraction of the total Y thickness the head band must extend below
        ``y_max`` (default 0.55; manifest-overridable).
    band_frac:
        Superior Z-band fraction sampled from ``z_max`` toward the feet
        (default 0.12; use 0.20 for headless meshes like Cosmic Buddha).

    Returns
    -------
    (passed, detail): tuple[bool, dict]
    """
    z = vertices[:, 2]
    y = vertices[:, 1]
    z_min, z_max = float(z.min()), float(z.max())
    y_min, y_max = float(y.min()), float(y.max())
    height_z = z_max - z_min
    thickness_y = y_max - y_min
    detail: dict = {
        "face_up_frac": face_up_frac,
        "band_frac": band_frac,
        "thickness_y": thickness_y,
    }
    if height_z <= 0 or thickness_y <= 0:
        detail["reason"] = "degenerate_extent"
        detail["passed"] = False
        return False, detail

    z_cut = z_max - band_frac * height_z
    band_mask = z >= z_cut
    if int(band_mask.sum()) < 10:
        detail["reason"] = "too_few_headband_points"
        detail["headband_points"] = int(band_mask.sum())
        detail["passed"] = False
        return False, detail

    y_min_headband = float(y[band_mask].min())
    threshold = y_max - face_up_frac * thickness_y
    passed = y_min_headband <= threshold
    detail.update(
        {
            "y_max": y_max,
            "y_min_headband": y_min_headband,
            "threshold": threshold,
            "headband_points": int(band_mask.sum()),
            "passed": passed,
        }
    )
    return passed, detail


def not_side_lying_ok(
    vertices: np.ndarray,
    *,
    band_frac: float = 0.12,
    max_lateral_over_ap: float = 1.35,
) -> tuple[bool, dict]:
    """Reject meshes whose superior band is much wider in X than in Y (side-lying).

    After PSD framing, a supine character should present face/chest protrusion
    primarily along Y (AP), not a wide lateral headband with a thin AP span.
    Side-lying fails when::

        headband_x_span > max_lateral_over_ap * headband_y_span
    """
    z = vertices[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    height_z = z_max - z_min
    detail: dict = {"band_frac": band_frac, "max_lateral_over_ap": max_lateral_over_ap}
    if height_z <= 0:
        detail["reason"] = "degenerate_extent"
        detail["passed"] = False
        return False, detail
    band_mask = z >= z_max - band_frac * height_z
    if int(band_mask.sum()) < 10:
        detail["reason"] = "too_few_headband_points"
        detail["headband_points"] = int(band_mask.sum())
        detail["passed"] = False
        return False, detail
    hb = vertices[band_mask]
    hx = float(hb[:, 0].max() - hb[:, 0].min())
    hy = float(hb[:, 1].max() - hb[:, 1].min())
    ratio = hx / max(hy, 1e-9)
    passed = ratio <= max_lateral_over_ap
    detail.update(
        {
            "headband_x_span": hx,
            "headband_y_span": hy,
            "lateral_over_ap": ratio,
            "passed": passed,
        }
    )
    return passed, detail


def _load_trimesh(path: Path):
    """Load ``path`` as a single concatenated ``trimesh.Trimesh`` (or raise)."""
    import trimesh

    safe = resolve_under_roots(path, must_be_file=True)
    mesh = trimesh.load(str(safe), force="mesh")  # NOSONAR pythonsecurity:S2083
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    return mesh


def _first_hit_face(
    origin: np.ndarray,
    direction: np.ndarray,
    triangles: np.ndarray,
    *,
    eps: float = 1e-8,
) -> int | None:
    """Return the index of the first triangle a ray hits (Moller-Trumbore).

    Vectorized over all ``triangles`` for a single ray. Returns the triangle
    index with the smallest positive ray parameter ``t`` or ``None`` if no hit.
    This is a dependency-free intersector (no rtree / embree backend needed).
    """
    v0 = triangles[:, 0, :]
    e1 = triangles[:, 1, :] - v0
    e2 = triangles[:, 2, :] - v0
    pvec = np.cross(direction, e2)
    det = np.einsum(_EINSUM_PAIRWISE_DOT, e1, pvec)
    valid = np.abs(det) > eps
    inv_det = np.zeros_like(det)
    inv_det[valid] = 1.0 / det[valid]
    tvec = origin - v0
    u = np.einsum(_EINSUM_PAIRWISE_DOT, tvec, pvec) * inv_det
    qvec = np.cross(tvec, e1)
    v = np.einsum("j,ij->i", direction, qvec) * inv_det
    t = np.einsum(_EINSUM_PAIRWISE_DOT, e2, qvec) * inv_det
    hit = valid & (u >= -eps) & (v >= -eps) & (u + v <= 1.0 + eps) & (t > eps)
    if not hit.any():
        return None
    hit_idx = np.where(hit)[0]
    return int(hit_idx[np.argmin(t[hit_idx])])


def outward_normals_ok(
    path: Path,
    *,
    n_samples: int = 200,
    seed: int = 0,
) -> tuple[bool, dict]:
    """Ray-cast gate that a majority of face normals point outward.

    For a random sample of face centroids, a ray is cast from **outside** the
    bounding box back toward the surface. At the first hit the hit-face normal
    ``n`` must oppose the ray direction (``dot(n, ray_direction) < 0``), meaning
    the surface faces back toward the (outside) ray origin. Fails if a majority
    of sampled hits point the wrong way (inward normals -> wrong entrance side
    in dose calc). Uses a dependency-free Moller-Trumbore intersector (no rtree
    or embree backend required).

    Returns ``(passed, detail)``. If trimesh is unavailable this raises; callers
    that reach this gate have already required trimesh.
    """
    mesh = _load_trimesh(path)
    detail: dict = {"n_requested": int(n_samples)}

    faces = np.asarray(mesh.faces)
    if len(faces) == 0:
        detail.update({"reason": "no_faces", "passed": False})
        return False, detail

    triangles = np.asarray(mesh.triangles, dtype=float)
    centroids = np.asarray(mesh.triangles_center, dtype=float)
    face_normals = np.asarray(mesh.face_normals, dtype=float)
    center = np.asarray(mesh.vertices, dtype=float).mean(axis=0)
    diag = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0]))
    if diag <= 0:
        detail.update({"reason": "degenerate_bounds", "passed": False})
        return False, detail

    rng = np.random.default_rng(seed)
    n = min(int(n_samples), len(centroids))
    idx = rng.choice(len(centroids), size=n, replace=False)

    # Outward direction from mesh center to each sampled centroid.
    out_dir = centroids[idx] - center
    norms = np.linalg.norm(out_dir, axis=1)
    keep = norms > 1e-9
    out_dir = out_dir[keep] / norms[keep, None]
    sample_centroids = centroids[idx][keep]
    if len(out_dir) < _MIN_NORMAL_SAMPLES:
        detail.update({"reason": "too_few_valid_samples", "n_valid": int(len(out_dir)), "passed": False})
        return False, detail

    # Origins well outside the bbox; rays travel back toward the surface.
    origins = sample_centroids + out_dir * diag
    directions = -out_dir

    outward = 0
    total = 0
    for origin, ray_dir in zip(origins, directions):
        tri = _first_hit_face(origin, ray_dir, triangles)
        if tri is None:
            continue
        total += 1
        if float(np.dot(face_normals[tri], ray_dir)) < 0.0:
            outward += 1

    if total < _MIN_NORMAL_SAMPLES:
        detail.update({"reason": "too_few_ray_hits", "n_hits": int(total), "passed": False})
        return False, detail

    frac = outward / float(total)
    passed = frac > 0.5
    detail.update(
        {
            "n_hits": total,
            "outward_hits": outward,
            "outward_fraction": frac,
            "passed": passed,
        }
    )
    return passed, detail


def phantom_load_ok(path: Path, name: str) -> tuple[bool, str]:
    try:
        from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
    except Exception as exc:  # noqa: BLE001
        return False, f"import_failed:{type(exc).__name__}"
    try:
        safe = resolve_under_roots(path, must_be_file=True)
        settings = PyskindoseSettings(load_settings_example_json())
        phantom = Phantom(
            phantom_model="human",
            phantom_dim=settings.phantom.dimension,
            human_mesh=(name, safe),
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
    require_trimesh: bool = False,
    face_up_frac: float = 0.55,
    face_up_band_frac: float = 0.12,
) -> dict:
    """Validate a phantom STL against the MyPySkinDose frame.

    Clinical mode (default) checks anchors, scale, a <=40k face ceiling, and
    optional shape metrics. Fun / demo mode (``require_trimesh=True``) is
    stricter for shipped non-clinical demo meshes: it hard-fails when trimesh is
    missing or the mesh is not watertight, enforces a <=20k face ceiling, and
    adds a face-up orientation gate and an outward-normal ray gate. See
    ``dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md``.
    """
    try:
        stl_path = resolve_under_roots(stl_path, must_exist=False)
        if compare_affine is not None:
            compare_affine = resolve_under_roots(compare_affine, must_be_file=True)
    except ValueError as exc:
        return {
            "file": str(stl_path),
            "passed": False,
            "require_trimesh": require_trimesh,
            "checks": {"path_confined": False, "path_error": str(exc)},
        }

    results: dict = {"file": str(stl_path), "passed": False, "require_trimesh": require_trimesh, "checks": {}}
    if not stl_path.exists():
        results["checks"]["exists"] = False
        return results
    results["checks"]["exists"] = True
    results["checks"]["path_confined"] = True

    max_faces = FUN_MAX_FACES if require_trimesh else CLINICAL_MAX_FACES
    faces = face_count(stl_path)
    results["checks"]["face_count"] = faces
    results["checks"]["face_count_ok"] = 1000 <= faces <= max_faces
    results["checks"]["face_count_ceiling"] = max_faces

    verts = load_vertices(stl_path)
    ext = extents(verts)
    results["checks"]["extents"] = ext
    results["checks"]["anchors_ok"] = (
        abs(ext["y_max"]) < 1.0 and abs(ext["z_max"]) < 1.0 and abs(ext["x_mid"]) < 1.0
    )
    results["checks"]["scale_ok"] = 50.0 < ext["height_z"] < 220.0

    wt = is_watertight(stl_path)
    results["checks"]["watertight"] = wt
    if require_trimesh:
        # Fun mode: trimesh must be installed (wt is None -> import failed) and
        # the mesh must be watertight. Never let an unrepaired mesh pass.
        results["checks"]["watertight_ok"] = wt is True
    else:
        results["checks"]["watertight_ok"] = wt is True or wt is None

    results["checks"]["head_ratio"] = head_ratio(verts)
    results["checks"]["abdomen_bulk"] = abdomen_bulk(verts)

    # Fun / demo gates: face-up orientation + outward normals.
    fun_ok = True
    if require_trimesh:
        fu_pass, fu_detail = face_up_ok(
            verts, face_up_frac=face_up_frac, band_frac=face_up_band_frac
        )
        results["checks"]["face_up"] = fu_detail
        results["checks"]["face_up_ok"] = fu_pass

        side_pass, side_detail = not_side_lying_ok(verts, band_frac=face_up_band_frac)
        results["checks"]["not_side_lying"] = side_detail
        results["checks"]["not_side_lying_ok"] = side_pass

        try:
            on_pass, on_detail = outward_normals_ok(stl_path)
        except ImportError as exc:
            on_pass, on_detail = False, {"reason": f"trimesh_missing:{exc}", "passed": False}
        results["checks"]["outward_normals"] = on_detail
        results["checks"]["outward_normals_ok"] = on_pass

        fun_ok = fu_pass and side_pass and on_pass

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
        and fun_ok
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path)
    parser.add_argument("--compare-affine", type=Path, default=None)
    parser.add_argument("--metric", choices=["head_ratio", "abdomen_bulk"], default=None)
    parser.add_argument("--metric-margin", type=float, default=0.05)
    parser.add_argument("--skip-phantom-load", action="store_true")
    parser.add_argument(
        "--require-trimesh",
        action="store_true",
        help=(
            "Fun / demo mode: hard-fail if trimesh missing or not watertight, "
            "enforce <=20k faces, and run face-up + outward-normal gates."
        ),
    )
    parser.add_argument(
        "--face-up-frac",
        type=float,
        default=0.55,
        help="Fraction of Y thickness the head band must reach toward -Y (fun mode).",
    )
    parser.add_argument(
        "--face-up-band-frac",
        type=float,
        default=0.12,
        help="Superior Z-band fraction for the face-up gate (use 0.20 for headless meshes).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        stl_path = resolve_under_roots(args.stl, must_exist=False)
        compare_affine = (
            resolve_under_roots(args.compare_affine, must_be_file=True)
            if args.compare_affine is not None
            else None
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    results = validate(
        stl_path,
        compare_affine=compare_affine,
        metric=args.metric,
        metric_margin=args.metric_margin,
        skip_phantom_load=args.skip_phantom_load,
        require_trimesh=args.require_trimesh,
        face_up_frac=args.face_up_frac,
        face_up_band_frac=args.face_up_band_frac,
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
