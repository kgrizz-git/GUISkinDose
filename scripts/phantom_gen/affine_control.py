#!/usr/bin/env python3
"""Build a stretch-only affine control STL matched to a candidate's bbox.

Used only for anti-balloon shape tests — never shipped as a phantom.

Usage::

    python scripts/phantom_gen/affine_control.py \\
      --base src/mypyskindose/phantom_data/adult_male.stl \\
      --match tmp/phantom_gen/spike_pediatric.stl \\
      -o tmp/phantom_gen/control_pediatric.stl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from stl import mesh as stl_mesh

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.phantom_gen.path_safety import resolve_under_roots  # noqa: E402


def _load(path: Path) -> tuple[np.ndarray, stl_mesh.Mesh]:
    safe = resolve_under_roots(path, must_be_file=True)
    m = stl_mesh.Mesh.from_file(str(safe))  # NOSONAR pythonsecurity:S2083
    verts = m.vectors.reshape(-1, 3).astype(float)
    return verts, m


def _spans(verts: np.ndarray) -> np.ndarray:
    return verts.max(axis=0) - verts.min(axis=0)


def build_affine_control(
    base_stl: Path,
    match_stl: Path,
    out_stl: Path,
    *,
    mode: str = "uniform_height",
) -> dict:
    base_verts, base_mesh = _load(base_stl)
    match_verts, _ = _load(match_stl)

    base_span = _spans(base_verts)
    match_span = _spans(match_verts)

    if mode == "uniform_height":
        s = float(match_span[2] / max(base_span[2], 1e-9))
        scale = np.array([s, s, s], dtype=float)
    elif mode == "anisotropic_bbox":
        scale = match_span / np.maximum(base_span, 1e-9)
    else:
        raise ValueError(f"unknown mode {mode}")

    anchor = np.array(
        [
            0.5 * (base_verts[:, 0].min() + base_verts[:, 0].max()),
            base_verts[:, 1].max(),
            base_verts[:, 2].max(),
        ]
    )
    scaled = anchor + (base_verts - anchor) * scale
    scaled[:, 0] -= 0.5 * (scaled[:, 0].min() + scaled[:, 0].max())
    scaled[:, 1] -= scaled[:, 1].max()
    scaled[:, 2] -= scaled[:, 2].max()

    out = stl_mesh.Mesh(np.zeros(base_mesh.vectors.shape[0], dtype=stl_mesh.Mesh.dtype))
    out.vectors = scaled.reshape(-1, 3, 3)
    safe_out = resolve_under_roots(out_stl, must_exist=False)
    safe_out.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(safe_out))  # NOSONAR pythonsecurity:S2083

    return {
        "mode": mode,
        "scale": scale.tolist(),
        "match_span": match_span.tolist(),
        "out_span": _spans(scaled).tolist(),
        "out": safe_out.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--match", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=["uniform_height", "anisotropic_bbox"],
        default="uniform_height",
        help="uniform_height preserves base shape ratios (default); anisotropic_bbox matches all extents",
    )
    args = parser.parse_args()
    info = build_affine_control(args.base, args.match, args.output, mode=args.mode)
    print(f"AFFINE_CONTROL_OK {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
