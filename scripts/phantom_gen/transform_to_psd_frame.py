#!/usr/bin/env python3
"""Transform an MPFB/Blender standing mesh into MyPySkinDose phantom frame.

Assumes Blender/MPFB Z-up standing humans with posterior toward +Y (typical).
Converts meters→cm when the height span is < 3.0, re-anchors to:
  x_mid = 0, y_max = 0 (back on table), z_max = 0 (head top).

Usage::

    python scripts/phantom_gen/transform_to_psd_frame.py in.obj -o out.stl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.phantom_gen.path_safety import resolve_under_roots  # noqa: E402


def _load_obj(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Minimal Wavefront OBJ loader (triangulated faces; no materials)."""
    safe = resolve_under_roots(path, must_be_file=True)
    vertices: list[list[float]] = []
    faces: list[list[int]] = []
    with safe.open(encoding="utf-8", errors="replace") as handle:  # NOSONAR pythonsecurity:S2083
        for line in handle:
            if line.startswith("v "):
                parts = line.split()
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif line.startswith("f "):
                parts = line.split()[1:]
                idxs: list[int] = []
                for part in parts:
                    # OBJ is 1-indexed; formats: v, v/vt, v/vt/vn, v//vn
                    idxs.append(int(part.split("/")[0]) - 1)
                if len(idxs) < 3:
                    continue
                # Fan-triangulate polygons
                for i in range(1, len(idxs) - 1):
                    faces.append([idxs[0], idxs[i], idxs[i + 1]])
    if not vertices or not faces:
        raise ValueError(f"OBJ has no geometry: {safe.name}")
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def _load_vertices_faces(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load mesh vertices/faces from OBJ (stdlib) or STL (numpy-stl / optional trimesh)."""
    safe = resolve_under_roots(path, must_be_file=True)
    suffix = safe.suffix.lower()
    if suffix == ".obj":
        return _load_obj(safe)

    if suffix in {".stl", ".stl.gz"}:
        from stl import mesh as stl_mesh

        m = stl_mesh.Mesh.from_file(str(safe))  # NOSONAR pythonsecurity:S2083
        # Unique vertices are not required for transform; keep triangle soup topology.
        faces = np.arange(len(m.vectors) * 3, dtype=np.int64).reshape(-1, 3)
        vertices = m.vectors.reshape(-1, 3).astype(float)
        return vertices, faces

    # Fallback for other formats when trimesh is available.
    try:
        import trimesh
    except ImportError as exc:
        raise ImportError(f"unsupported mesh format {suffix}; install trimesh or use OBJ/STL") from exc

    mesh = trimesh.load(str(safe), force="mesh")  # NOSONAR pythonsecurity:S2083
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(tuple(mesh.geometry.values()))
    vertices = np.asarray(mesh.vertices, dtype=float)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    return vertices, faces


def _write_binary_stl(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    from stl import mesh as stl_mesh

    safe = resolve_under_roots(path, must_exist=False)
    stl = stl_mesh.Mesh(np.zeros(faces.shape[0], dtype=stl_mesh.Mesh.dtype))
    for i, tri in enumerate(faces):
        for j in range(3):
            stl.vectors[i][j] = vertices[tri[j]]
    safe.parent.mkdir(parents=True, exist_ok=True)
    stl.save(str(safe))  # NOSONAR pythonsecurity:S2083


def _remap_obj_y_up_to_z_up(vertices: np.ndarray) -> np.ndarray:
    """Blender ``wm.obj_export`` writes Y-up: (x, y_up, z_depth) → (x, z_depth, y_up)."""
    v = np.asarray(vertices, dtype=float)
    return np.column_stack((v[:, 0], v[:, 2], v[:, 1]))


def transform_to_psd_frame(
    vertices: np.ndarray,
    *,
    meters_to_cm_if_small: bool = True,
    flip_y_if_needed: bool = True,
    force_flip_y: bool = False,
    obj_y_up: bool = True,
) -> np.ndarray:
    """Return transformed vertex array (cm, PSD anchors).

    Face-up supine convention: posterior/back at ``max(Y) ≈ 0`` (table), anterior
    toward −Y. MPFB/Blender OBJ exports are often near-symmetric in Y after remap, so
    the asymmetric ``flip_y_if_needed`` heuristic is a no-op and can leave meshes
    **face-down**. Pass ``force_flip_y=True`` for MPFB catalog generation.
    """
    v = np.asarray(vertices, dtype=float).copy()
    if obj_y_up:
        v = _remap_obj_y_up_to_z_up(v)

    spans = v.max(axis=0) - v.min(axis=0)
    # Height is along Z after remap
    height = float(spans[2])
    if meters_to_cm_if_small and height < 3.0:
        v *= 100.0

    # Posterior should be max Y.
    if force_flip_y:
        v[:, 1] *= -1.0
    elif flip_y_if_needed:
        y_min, y_max = float(v[:, 1].min()), float(v[:, 1].max())
        y_mid = 0.5 * (y_min + y_max)
        if abs(y_min - y_mid) < abs(y_max - y_mid):
            v[:, 1] *= -1.0

    x_mid = 0.5 * (float(v[:, 0].min()) + float(v[:, 0].max()))
    v[:, 0] -= x_mid
    v[:, 1] -= float(v[:, 1].max())
    v[:, 2] -= float(v[:, 2].max())
    return v


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input OBJ/STL")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output binary STL")
    parser.add_argument("--no-unit-detect", action="store_true")
    parser.add_argument("--no-flip-y", action="store_true")
    parser.add_argument(
        "--force-flip-y",
        action="store_true",
        help="Always flip Y before anchoring (MPFB catalog; overrides heuristic)",
    )
    parser.add_argument(
        "--no-obj-y-up",
        action="store_true",
        help="Skip Blender OBJ Y-up remapping (input already Z-up)",
    )
    args = parser.parse_args()

    try:
        input_path = resolve_under_roots(args.input, must_be_file=True)
        output_path = resolve_under_roots(args.output, must_exist=False)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    vertices, faces = _load_vertices_faces(input_path)
    transformed = transform_to_psd_frame(
        vertices,
        meters_to_cm_if_small=not args.no_unit_detect,
        flip_y_if_needed=not args.no_flip_y and not args.force_flip_y,
        force_flip_y=args.force_flip_y,
        obj_y_up=not args.no_obj_y_up,
    )
    _write_binary_stl(output_path, transformed, faces)

    spans = transformed.max(axis=0) - transformed.min(axis=0)
    print(
        "TRANSFORM_OK "
        f"faces={len(faces)} "
        f"x=[{transformed[:, 0].min():.2f},{transformed[:, 0].max():.2f}] "
        f"y=[{transformed[:, 1].min():.2f},{transformed[:, 1].max():.2f}] "
        f"z=[{transformed[:, 2].min():.2f},{transformed[:, 2].max():.2f}] "
        f"spans=({spans[0]:.1f},{spans[1]:.1f},{spans[2]:.1f}) "
        f"out={output_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
