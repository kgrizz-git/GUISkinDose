#!/usr/bin/env python3
"""Decimate a PSD-frame STL to a ~1000-triangle preview mesh.

Writes ``{stem}_reduced_1000t.stl`` next to the input (or under ``--out-dir``).

Usage::

    python scripts/phantom_gen/generate_reduced.py tmp/phantom_gen/p0/pediatric_5y_male.stl
    python scripts/phantom_gen/generate_reduced.py tmp/phantom_gen/p0/*.stl --out-dir tmp/phantom_gen/p0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from stl import mesh as stl_mesh


def _load_triangle_soup(path: Path) -> np.ndarray:
    m = stl_mesh.Mesh.from_file(str(path))
    return np.asarray(m.vectors, dtype=float).copy()


def _write_vectors(path: Path, vectors: np.ndarray) -> None:
    out = stl_mesh.Mesh(np.zeros(vectors.shape[0], dtype=stl_mesh.Mesh.dtype))
    out.vectors = vectors
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(path))


def decimate_to_target_faces(
    vectors: np.ndarray,
    *,
    target_faces: int = 1000,
) -> np.ndarray:
    """Return a triangle-soup with approximately ``target_faces`` faces.

    Prefers ``trimesh`` quadric decimation when available; otherwise uniformly
    subsamples existing triangles (preview-quality fallback).
    """
    n = int(vectors.shape[0])
    if n <= target_faces:
        return vectors

    try:
        import trimesh
    except ImportError:
        trimesh = None

    if trimesh is not None:
        # Rebuild indexed mesh, then simplify.
        flat = vectors.reshape(-1, 3)
        faces = np.arange(flat.shape[0], dtype=np.int64).reshape(-1, 3)
        mesh = trimesh.Trimesh(vertices=flat, faces=faces, process=True)
        try:
            simplified = mesh.simplify_quadric_decimation(face_count=target_faces)
            return np.asarray(simplified.triangles, dtype=float)
        except Exception:  # noqa: BLE001 — fall through to subsample
            pass

    # Uniform triangle subsample (deterministic).
    rng = np.random.default_rng(0)
    idx = np.sort(rng.choice(n, size=target_faces, replace=False))
    return vectors[idx]


def generate_reduced(
    stl_path: Path,
    *,
    out_path: Path | None = None,
    target_faces: int = 1000,
) -> Path:
    """Write reduced STL; return output path."""
    vectors = _load_triangle_soup(stl_path)
    reduced = decimate_to_target_faces(vectors, target_faces=target_faces)
    if out_path is None:
        out_path = stl_path.with_name(f"{stl_path.stem}_reduced_{target_faces}t.stl")
    _write_vectors(out_path, reduced)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Input STL path(s)")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--target-faces", type=int, default=1000)
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
            out = generate_reduced(src, out_path=dest, target_faces=args.target_faces)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {src.name}: {type(exc).__name__}:{exc}", file=sys.stderr)
            failures += 1
            continue
        print(f"REDUCED_OK in={src.name} out={out.name} faces≈{args.target_faces}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
