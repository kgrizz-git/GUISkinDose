#!/usr/bin/env python3
"""Build or verify the maintainer phantom pack zip (writes under tmp/ only)."""

from __future__ import annotations

import argparse
import hashlib
import sys
import tomllib
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PHANTOM_DATA = REPO_ROOT / "src" / "guiskindose" / "phantom_data"


def _load_version() -> str:
    """Read the wheel version from ``pyproject.toml`` (no import of ``guiskindose``)."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise SystemExit("pyproject.toml is missing [project].version")
    return version


def _pack_stl_paths() -> list[Path]:
    """Return the shipped STLs that belong in the pack: everything outside the Light starter set, minus legacy _reduced_1000t previews."""
    from guiskindose.edition import light_phantom_stl_names

    light_names = set(light_phantom_stl_names())
    paths: list[Path] = []
    for stl in sorted(PHANTOM_DATA.glob("*.stl")):
        if stl.name in light_names:
            continue
        if stl.name.endswith("_reduced_1000t.stl"):
            continue
        paths.append(stl)
    return paths


def build_pack_manifest(paths: list[Path], *, app_version: str) -> dict:
    """Build the format-1 manifest for *paths*, with each file's byte count and SHA-256, sorted by stem."""
    files = []
    for path in paths:
        data = path.read_bytes()
        files.append(
            {
                "stem": path.stem,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    files.sort(key=lambda item: item["stem"])
    return {
        "format": 1,
        "pack_version": app_version,
        "app_versions": [app_version],
        "files": files,
    }


def write_pack_zip(manifest: dict, paths: list[Path], out_zip: Path) -> None:
    """Write the canonical manifest and the STLs, named by stem, into a deflated zip at *out_zip*."""
    from guiskindose.phantom_pack import canonical_manifest_bytes

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest_name = "manifest.json"
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(manifest_name, canonical_manifest_bytes(manifest))
        for path in paths:
            zf.write(path, arcname=f"{path.stem}.stl")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or verify the phantom pack zip.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify EXPECTED_PHANTOM_PACK_SHA256 matches a freshly built manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "tmp" / "phantom_pack.zip",
        help="Zip output path (default: tmp/phantom_pack.zip).",
    )
    return parser.parse_args()


def main() -> int:
    """Build the pack zip, or with --check compare the committed pin to a freshly built manifest digest."""
    args = _parse_args()
    app_version = _load_version()
    paths = _pack_stl_paths()
    from guiskindose.phantom_pack import canonical_manifest_bytes, validate_manifest_for_install

    manifest = build_pack_manifest(paths, app_version=app_version)
    validate_manifest_for_install(manifest, app_version=app_version)
    digest = hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()
    if args.check:
        from guiskindose.phantom_pack_pin import EXPECTED_PHANTOM_PACK_SHA256

        if not EXPECTED_PHANTOM_PACK_SHA256:
            print("EXPECTED_PHANTOM_PACK_SHA256 is empty; pin check refused.", file=sys.stderr)
            return 1
        if digest != EXPECTED_PHANTOM_PACK_SHA256:
            print("Phantom pack manifest pin mismatch.", file=sys.stderr)
            return 1
        print("Phantom pack manifest pin OK.")
        return 0
    write_pack_zip(manifest, paths, args.output)
    print(f"Wrote pack ({len(paths)} meshes); manifest sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
