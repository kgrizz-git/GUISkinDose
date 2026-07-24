#!/usr/bin/env python3
"""Decimate a PSD-frame STL to a ~3000-triangle preview mesh.

Writes ``{stem}_reduced_3000t.stl`` next to the input (or under ``--out-dir``).

Requires ``trimesh`` and ``fast-simplification`` for shipping-quality output
(quadric edge collapse). Uniform triangle subsample is intentionally *not*
the default: it yields disconnected fragments that look like scatter in
Plotly Mesh3d previews (Settings tab).

Install::

    pip install "trimesh>=4" "fast-simplification"

Usage::

    python scripts/phantom_gen/generate_reduced.py tmp/phantom_gen/p0/ped_5y_male.stl
    python scripts/phantom_gen/generate_reduced.py tmp/phantom_gen/p0/*.stl --out-dir tmp/phantom_gen/p0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from stl import mesh as stl_mesh

# Connected preview meshes share vertices heavily; triangle-subsample soups do not.
_MAX_UNIQUE_VERTS_PER_FACE = 1.2


def _load_triangle_soup(path: Path) -> np.ndarray:
    m = stl_mesh.Mesh.from_file(str(path))
    return np.asarray(m.vectors, dtype=float).copy()


def _write_vectors(path: Path, vectors: np.ndarray) -> None:
    out = stl_mesh.Mesh(np.zeros(vectors.shape[0], dtype=stl_mesh.Mesh.dtype))
    out.vectors = vectors
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(path))


def unique_vertex_count(vectors: np.ndarray, *, decimals: int = 5) -> int:
    """Count approximately unique vertices in a triangle-soup array."""
    flat = np.asarray(vectors, dtype=float).reshape(-1, 3)
    if flat.size == 0:
        return 0
    return int(len(np.unique(np.round(flat, decimals), axis=0)))


def assert_connected_preview(vectors: np.ndarray, *, label: str = "mesh") -> None:
    """Fail if ``vectors`` looks like a disconnected triangle subsample."""
    n_faces = int(np.asarray(vectors).shape[0])
    if n_faces <= 0:
        raise ValueError(f"{label}: empty triangle list")
    uniq = unique_vertex_count(vectors)
    ratio = uniq / float(n_faces)
    if ratio > _MAX_UNIQUE_VERTS_PER_FACE:
        raise RuntimeError(
            f"{label}: preview mesh looks disconnected "
            f"(unique_verts/faces={ratio:.2f}, uniq={uniq}, faces={n_faces}). "
            "Install trimesh + fast-simplification and re-run without --allow-subsample."
        )


def _subsample_triangles(vectors: np.ndarray, target_faces: int) -> np.ndarray:
    """Deterministic uniform triangle subsample (emergency / unit-test only)."""
    n = int(vectors.shape[0])
    rng = np.random.default_rng(0)
    idx = np.sort(rng.choice(n, size=target_faces, replace=False))
    return vectors[idx]


def decimate_to_target_faces(
    vectors: np.ndarray,
    *,
    target_faces: int = 3000,
    allow_subsample: bool = False,
) -> np.ndarray:
    """Return a triangle-soup with approximately ``target_faces`` faces.

    Uses ``trimesh`` quadric decimation via ``fast-simplification``. Raises if
    that path is unavailable unless ``allow_subsample=True``.
    """
    n = int(vectors.shape[0])
    if n <= target_faces:
        return vectors

    try:
        import trimesh
    except ImportError as exc:
        if allow_subsample:
            return _subsample_triangles(vectors, target_faces)
        raise RuntimeError(
            "trimesh is required for shipping-quality reduced phantoms. "
            'Install with: pip install "trimesh>=4" "fast-simplification"'
        ) from exc

    flat = vectors.reshape(-1, 3)
    faces = np.arange(flat.shape[0], dtype=np.int64).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=flat, faces=faces, process=True)
    try:
        simplified = mesh.simplify_quadric_decimation(face_count=target_faces)
    except Exception as exc:  # noqa: BLE001 — missing fast-simplification, etc.
        if allow_subsample:
            return _subsample_triangles(vectors, target_faces)
        raise RuntimeError(
            "quadric decimation failed (is fast-simplification installed?). "
            'Install with: pip install "trimesh>=4" "fast-simplification". '
            "Use --allow-subsample only for tests/emergencies."
        ) from exc

    reduced = np.asarray(simplified.triangles, dtype=float)
    assert_connected_preview(reduced, label="quadric-decimated preview")
    return reduced


def generate_reduced(
    stl_path: Path,
    *,
    out_path: Path | None = None,
    target_faces: int = 3000,
    allow_subsample: bool = False,
) -> Path:
    """Write reduced STL; return output path."""
    vectors = _load_triangle_soup(stl_path)
    reduced = decimate_to_target_faces(
        vectors,
        target_faces=target_faces,
        allow_subsample=allow_subsample,
    )
    if out_path is None:
        out_path = stl_path.with_name(f"{stl_path.stem}_reduced_{target_faces}t.stl")
    if not allow_subsample:
        assert_connected_preview(reduced, label=out_path.name)
    _write_vectors(out_path, reduced)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Input STL path(s)")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--target-faces", type=int, default=3000)
    parser.add_argument(
        "--allow-subsample",
        action="store_true",
        help="Permit disconnected triangle subsample (tests/emergencies only)",
    )
    args = parser.parse_args(argv)

    failures = 0
    for src in args.inputs:
        if not src.is_file():
            print(f"ERROR: missing {src}", file=sys.stderr)
            failures += 1
            continue
        if args.out_dir is not None:
            dest = args.out_dir / f"{src.stem}_reduced_{args.target_faces}t.stl"
        else:
            dest = None
        try:
            out = generate_reduced(
                src,
                out_path=dest,
                target_faces=args.target_faces,
                allow_subsample=args.allow_subsample,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {src.name}: {type(exc).__name__}:{exc}", file=sys.stderr)
            failures += 1
            continue
        uniq = unique_vertex_count(_load_triangle_soup(out))
        print(
            f"REDUCED_OK in={src.name} out={out.name} "
            f"faces≈{args.target_faces} unique_verts≈{uniq}"
        )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
