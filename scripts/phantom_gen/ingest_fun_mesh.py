#!/usr/bin/env python3
"""Ingest a fun / demo (non-clinical) statue or cartoon mesh into the PSD frame.

This is the orientation + repair + decimation pipeline for the demo phantoms
(Cosmic Buddha, Petite Herculanaise, Ramesses II, Steamboat Willie). It applies
a per-mesh Euler rotation, uniform-scales the chosen height axis to a target
height in centimeters, caps open boundaries, re-anchors into the GUISkinDose
PSD frame, re-fixes winding/normals **after** the flip (a Y-flip reverses
triangle handedness), decimates to a shipping face budget, and validates the
result with the fun-mode gates in ``validate_phantom.py``.

See ``dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md``.

Inputs
------
- ``--id``:          mesh stem (also used to pull locked defaults from the manifest)
- ``--input``:       source mesh (STL/OBJ/PLY) under ``tmp/fun_phantoms/raw/{id}/``
- ``--rotate-deg``:  ``rx,ry,rz`` Euler degrees (sxyz) applied to the raw mesh
- ``--height-cm``:   target span of the height axis after uniform scale
- ``--height-axis``: raw-mesh axis whose span is scaled (``x``|``y``|``z``)
- ``--target-faces``: shipping face budget (quadric decimation, no subsample)
- ``--flip-y`` / ``--no-flip-y``: map to ``force_flip_y`` (see plan flip contract)
- ``--face-up-frac`` / ``--face-up-band-frac``: fun-mode face-up gate tuning
- ``--voxel-pitch``: voxel edge (cm) for the marching-cubes watertight remesh
  (used instead of fill/cap for messy raw scans; needs ``scikit-image``)
- ``--out-dir``:     output directory for ``{id}.stl`` (e.g. ``tmp/fun_phantoms/psd``)
- ``--preview-only``: report post-transform extents/faces only; no write/validate
- ``--manifest``:    manifest JSON (defaults to ``fun_mesh_manifest.json`` beside this file)

Outputs
-------
- ``{out-dir}/{id}.stl`` (binary STL in the PSD frame; NOT installed into
  ``phantom_data/`` by this script).

Requirements
------------
- ``trimesh>=4`` and ``fast-simplification`` (``pip install -e ".[phantom-gen]"``).

Notes
-----
- Uses ``pathlib`` only; never logs absolute paths or PII of user data.
- Never passes ``--allow-subsample`` to the decimator for the shipping path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Allow ``python scripts/phantom_gen/ingest_fun_mesh.py`` without PYTHONPATH=.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.phantom_gen.generate_reduced import decimate_to_target_faces  # noqa: E402
from scripts.phantom_gen.path_safety import resolve_under_roots  # noqa: E402
from scripts.phantom_gen.transform_to_psd_frame import transform_to_psd_frame  # noqa: E402
from scripts.phantom_gen.validate_phantom import validate  # noqa: E402

_DEFAULT_MANIFEST = Path(__file__).resolve().parent / "fun_mesh_manifest.json"
_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def load_manifest(path: Path) -> dict:
    """Load the fun-mesh manifest JSON, returning the parsed dict."""
    safe = resolve_under_roots(path, must_be_file=True)
    with safe.open(encoding="utf-8") as handle:  # NOSONAR pythonsecurity:S2083
        return json.load(handle)


def manifest_entry(manifest: dict, mesh_id: str) -> dict:
    """Return the merged (defaults + per-mesh) manifest entry for ``mesh_id``.

    Raises ``KeyError`` if the id is not present. Per-mesh keys override the
    top-level ``defaults`` block.
    """
    meshes = manifest.get("meshes", {})
    if mesh_id not in meshes:
        raise KeyError(mesh_id)
    merged = dict(manifest.get("defaults", {}))
    merged.update(meshes[mesh_id])
    return merged


def _load_trimesh(path: Path):
    """Load ``path`` as a single concatenated ``trimesh.Trimesh`` (or raise)."""
    import trimesh

    mesh = trimesh.load(str(path), force="mesh")
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    return mesh


def _euler_matrix(rotate_deg: tuple[float, float, float]):
    """Build a 4x4 sxyz Euler rotation matrix from degrees."""
    import trimesh

    rx, ry, rz = (float(np.deg2rad(a)) for a in rotate_deg)
    return trimesh.transformations.euler_matrix(rx, ry, rz, axes="sxyz")


def _uniform_scale_to_height(mesh, *, height_cm: float, height_axis: str) -> float:
    """Uniform-scale ``mesh`` in place so ``height_axis`` span == ``height_cm``.

    Returns the applied scale factor. Uniform scaling preserves proportions.
    """
    axis = _AXIS_INDEX[height_axis]
    span = float(mesh.bounds[1][axis] - mesh.bounds[0][axis])
    if span <= 0:
        raise ValueError(f"height axis '{height_axis}' has non-positive span {span}")
    scale = height_cm / span
    mesh.apply_scale(scale)
    return scale


def _fill_and_fix(mesh) -> None:
    """Best-effort cap open boundaries and make normals consistent (in place).

    ``trimesh.Trimesh.fill_holes`` needs ``networkx`` (part of the ``phantom-gen``
    extra). It only closes simple boundary loops; meshes with wide-open bases or
    multiple disconnected bodies (raw museum scans) will not become watertight
    here — use ``_voxel_remesh_watertight`` (``--voxel-pitch``) for those.
    """
    import trimesh

    try:
        mesh.fill_holes()
    except Exception:  # noqa: BLE001 — repair is best-effort; watertight gate enforces
        pass
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_normals(mesh)


def _voxel_remesh_watertight(mesh, *, pitch: float):
    """Return a watertight, manifold remesh of ``mesh`` via voxel marching cubes.

    Raw statue/cartoon scans are frequently non-watertight (open bases, multiple
    disconnected bodies, self-intersections) that ``fill_holes`` cannot close. A
    solid-voxelization + marching-cubes remesh is a robust, cross-platform
    (pure ``trimesh`` + ``scipy`` + ``scikit-image``) way to produce a single
    closed manifold shell that preserves the overall silhouette — which is what
    the PSD entrance/exit geometry depends on.

    ``pitch`` is the voxel edge length in the *current* mesh units (centimetres,
    because scaling to ``height_cm`` runs before this step). Choose a pitch that
    yields a face count at or below the shipping ``target_faces`` so the later
    quadric-decimation step is a no-op and cannot reintroduce non-manifold edges
    (aggressive quadric decimation of a marching-cubes mesh can break
    watertightness). ``marching_cubes`` output is in voxel-index coordinates, so
    the grid ``transform`` is applied to return to world (cm) coordinates.

    Requires ``scikit-image`` (for ``skimage.measure.marching_cubes``, used by
    ``trimesh.voxel``) and ``scipy`` (solid ``fill``); both ship in the
    ``phantom-gen`` extra.
    """
    import trimesh

    voxels = mesh.voxelized(pitch=pitch).fill()
    remeshed = voxels.marching_cubes
    remeshed.apply_transform(voxels.transform)  # voxel-index -> world (cm)
    remeshed.merge_vertices()
    trimesh.repair.fix_winding(remeshed)
    trimesh.repair.fix_normals(remeshed)
    return remeshed


def _trimesh_from_soup(vectors: np.ndarray):
    """Build a processed (vertex-merged) Trimesh from a triangle-soup array."""
    import trimesh

    flat = np.asarray(vectors, dtype=float).reshape(-1, 3)
    faces = np.arange(flat.shape[0], dtype=np.int64).reshape(-1, 3)
    return trimesh.Trimesh(vertices=flat, faces=faces, process=True)


def ingest_fun_mesh(
    *,
    mesh_id: str,
    input_path: Path,
    rotate_deg: tuple[float, float, float],
    height_cm: float,
    height_axis: str,
    target_faces: int,
    flip_y: bool,
    out_dir: Path,
    face_up_frac: float = 0.55,
    face_up_band_frac: float = 0.12,
    voxel_pitch: float | None = None,
    preview_only: bool = False,
) -> dict:
    """Run the full fun-mesh ingest pipeline and return a report dict.

    Pipeline: load -> Euler rotate -> uniform scale to ``height_cm`` ->
    fill/cap **or** voxel remesh -> PSD transform (``obj_y_up=False``,
    ``meters_to_cm_if_small=False``, ``force_flip_y=flip_y``,
    ``flip_y_if_needed=False``) -> re-fix winding/normals -> quadric decimate
    (no subsample) -> re-fix normals -> write ``{id}.stl`` -> validate (fun mode)
    unless ``preview_only``.

    When ``voxel_pitch`` is set, the fill/cap step is replaced by a solid
    voxel + marching-cubes remesh (``_voxel_remesh_watertight``). This is the
    locked repair path for raw scans that ``fill_holes`` cannot close (open
    bases, multiple disconnected bodies — e.g. Ramesses II). Choose a pitch that
    yields at most ``target_faces`` faces so the later decimation is a no-op and
    the watertight/manifold result survives to the shipped STL.
    """
    import trimesh

    report: dict = {"id": mesh_id, "preview_only": preview_only, "voxel_pitch": voxel_pitch}

    mesh = _load_trimesh(input_path)
    report["raw_faces"] = int(len(mesh.faces))

    # 1) Euler rotate (degrees, sxyz).
    mesh.apply_transform(_euler_matrix(rotate_deg))

    # 2) Uniform scale so the height-axis span == height_cm.
    report["scale"] = _uniform_scale_to_height(mesh, height_cm=height_cm, height_axis=height_axis)

    # 3) Cap open boundaries. Watertight-by-fill for meshes with simple holes;
    #    voxel remesh for messy raw scans (locked per-mesh via voxel_pitch).
    if voxel_pitch is not None:
        mesh = _voxel_remesh_watertight(mesh, pitch=float(voxel_pitch))
        report["remesh_faces"] = int(len(mesh.faces))
        report["remesh_watertight"] = bool(mesh.is_watertight)
    else:
        _fill_and_fix(mesh)

    # 4) PSD anchor. Input is already Z-up (rotated) and in cm, so disable the
    #    OBJ Y-up remap and the meters->cm auto-detect. flip_y is locked, so the
    #    asymmetric heuristic is disabled and force_flip_y is explicit.
    transformed = transform_to_psd_frame(
        mesh.vertices,
        meters_to_cm_if_small=False,
        flip_y_if_needed=False,
        force_flip_y=flip_y,
        obj_y_up=False,
    )
    psd = trimesh.Trimesh(vertices=transformed, faces=mesh.faces, process=False)

    # 5) Re-fix winding/normals AFTER the transform (a Y-flip reverses handedness).
    trimesh.repair.fix_winding(psd)
    trimesh.repair.fix_normals(psd)

    ext = {
        "x_mid": float(0.5 * (psd.vertices[:, 0].min() + psd.vertices[:, 0].max())),
        "y_max": float(psd.vertices[:, 1].max()),
        "z_max": float(psd.vertices[:, 2].max()),
        "height_z": float(psd.vertices[:, 2].max() - psd.vertices[:, 2].min()),
    }
    report["post_transform_extents"] = ext
    report["post_transform_faces"] = int(len(psd.faces))

    if preview_only:
        report["written"] = None
        report["validated"] = False
        return report

    # 6) Quadric decimate to the shipping budget (never subsample for shipping).
    reduced_soup = decimate_to_target_faces(
        np.asarray(psd.triangles, dtype=float),
        target_faces=target_faces,
        allow_subsample=False,
    )
    final = _trimesh_from_soup(reduced_soup)

    # 7) Re-fix normals again (decimation rebuilds face normals).
    trimesh.repair.fix_winding(final)
    trimesh.repair.fix_normals(final)
    report["final_faces"] = int(len(final.faces))

    # 8) Write {id}.stl (binary STL) under out-dir. NOT installed to phantom_data/.
    safe_out_dir = resolve_under_roots(out_dir, must_exist=False)
    safe_out_dir.mkdir(parents=True, exist_ok=True)
    out_path = resolve_under_roots(safe_out_dir / f"{mesh_id}.stl", must_exist=False)
    final.export(str(out_path), file_type="stl")  # NOSONAR pythonsecurity:S2083
    report["written"] = str(out_path)

    # 9) Validate in fun mode (watertight True, <=20k faces, face-up, normals).
    results = validate(
        out_path,
        require_trimesh=True,
        face_up_frac=face_up_frac,
        face_up_band_frac=face_up_band_frac,
    )
    report["validated"] = True
    report["validation_passed"] = bool(results["passed"])
    report["validation"] = results
    return report


def _parse_rotate_deg(text: str) -> tuple[float, float, float]:
    """Parse ``rx,ry,rz`` degrees into a 3-tuple of floats."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("--rotate-deg must be 'rx,ry,rz'")
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", required=True, help="Mesh stem (also keys manifest defaults)")
    parser.add_argument("--input", type=Path, required=True, help="Source STL/OBJ/PLY")
    parser.add_argument("--rotate-deg", type=_parse_rotate_deg, default=None, help="'rx,ry,rz' Euler degrees")
    parser.add_argument("--height-cm", type=float, default=None, help="Target height-axis span (cm)")
    parser.add_argument("--height-axis", choices=["x", "y", "z"], default=None, help="Raw axis to scale")
    parser.add_argument("--target-faces", type=int, default=None, help="Shipping face budget")
    flip_group = parser.add_mutually_exclusive_group()
    flip_group.add_argument("--flip-y", dest="flip_y", action="store_true", default=None, help="force_flip_y=True")
    flip_group.add_argument("--no-flip-y", dest="flip_y", action="store_false", help="force_flip_y=False")
    parser.add_argument("--face-up-frac", type=float, default=None, help="Face-up Y-thickness fraction")
    parser.add_argument("--face-up-band-frac", type=float, default=None, help="Face-up superior Z-band fraction")
    parser.add_argument(
        "--voxel-pitch",
        type=float,
        default=None,
        help=(
            "Voxel edge length (cm) for the marching-cubes watertight remesh used "
            "instead of fill/cap for messy raw scans. Pick a pitch that yields "
            "<= target-faces faces so decimation stays a no-op."
        ),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("tmp/fun_phantoms/psd"), help="Output directory")
    parser.add_argument("--preview-only", action="store_true", help="Report extents/faces; no write/validate")
    parser.add_argument("--manifest", type=Path, default=_DEFAULT_MANIFEST, help="fun_mesh_manifest.json path")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"ERROR: input not found: {args.input}", file=sys.stderr)
        return 1

    # Merge CLI overrides on top of manifest-locked defaults for this id.
    entry: dict = {}
    if args.manifest.exists():
        try:
            entry = manifest_entry(load_manifest(args.manifest), args.id)
        except KeyError:
            print(f"WARNING: id '{args.id}' not in manifest; using CLI values only", file=sys.stderr)

    def pick(cli_value, key, default=None):
        if cli_value is not None:
            return cli_value
        return entry.get(key, default)

    rotate_deg = pick(args.rotate_deg, "rotate_deg", (0.0, 0.0, 0.0))
    rotate_deg = tuple(float(v) for v in rotate_deg)
    height_cm = pick(args.height_cm, "height_cm")
    height_axis = pick(args.height_axis, "height_axis", "z")
    target_faces = int(pick(args.target_faces, "target_faces", 6000))
    flip_y = pick(args.flip_y, "flip_y", False)
    face_up_frac = float(pick(args.face_up_frac, "face_up_frac", 0.55))
    face_up_band_frac = float(pick(args.face_up_band_frac, "face_up_band_frac", 0.12))
    voxel_pitch_val = pick(args.voxel_pitch, "voxel_pitch", None)
    voxel_pitch = float(voxel_pitch_val) if voxel_pitch_val is not None else None

    if height_cm is None:
        print("ERROR: --height-cm is required (not found in manifest)", file=sys.stderr)
        return 1

    try:
        report = ingest_fun_mesh(
            mesh_id=args.id,
            input_path=args.input,
            rotate_deg=rotate_deg,  # type: ignore[arg-type]
            height_cm=float(height_cm),
            height_axis=height_axis,
            target_faces=target_faces,
            flip_y=bool(flip_y),
            out_dir=args.out_dir,
            face_up_frac=face_up_frac,
            face_up_band_frac=face_up_band_frac,
            voxel_pitch=voxel_pitch,
            preview_only=args.preview_only,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL {args.id}: {type(exc).__name__}:{exc}", file=sys.stderr)
        return 1

    ext = report.get("post_transform_extents", {})
    print(
        f"INGEST {'PREVIEW' if args.preview_only else 'OK'} id={report['id']} "
        f"raw_faces={report.get('raw_faces')} scale={report.get('scale'):.4f} "
        f"post_faces={report.get('post_transform_faces')} "
        f"x_mid={ext.get('x_mid', float('nan')):.2f} y_max={ext.get('y_max', float('nan')):.2f} "
        f"z_max={ext.get('z_max', float('nan')):.2f} height_z={ext.get('height_z', float('nan')):.1f}"
    )
    if args.preview_only:
        return 0

    print(
        f"INGEST WROTE {report.get('written')} final_faces={report.get('final_faces')} "
        f"validation_passed={report.get('validation_passed')}"
    )
    return 0 if report.get("validation_passed") else 1


if __name__ == "__main__":
    sys.exit(main())
