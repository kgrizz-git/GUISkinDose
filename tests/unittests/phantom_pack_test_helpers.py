"""Shared helpers for phantom pack unit tests."""

from __future__ import annotations

import hashlib
import io
import zipfile
from typing import Any


def manifest_for_files(
    files: dict[str, bytes],
    *,
    app_version: str = "1.1.1",
) -> dict[str, Any]:
    entries = []
    for stem in sorted(files):
        data = files[stem]
        entries.append(
            {
                "stem": stem,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return {
        "format": 1,
        "pack_version": app_version,
        "app_versions": [app_version],
        "files": entries,
    }


def pack_zip_bytes(manifest: dict[str, Any], files: dict[str, bytes]) -> bytes:
    from guiskindose.phantom_pack import canonical_manifest_bytes

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", canonical_manifest_bytes(manifest))
        for stem, data in files.items():
            zf.writestr(f"{stem}.stl", data)
    return buffer.getvalue()


def tiny_stl_body() -> bytes:
    return b"solid t\nendsolid t\n"
