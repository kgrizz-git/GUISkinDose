"""Helpers for DoseTrack / CID 10003 plane-code maps."""

from __future__ import annotations

import json

from guiskindose.constants import DOSETRACK_PLANE_MEANINGS


def parse_plane_code_map(raw: object) -> dict[int, str] | None:
    """Parse an explicit DoseTrack plane-code map from settings or CLI text.

    Accepts:
    - ``None`` / empty → ``None``
    - ``dict`` with int-like keys and meaning values (``"Plane A"`` / ``"Plane B"`` /
      ``"Single Plane"``)
    - JSON object string, e.g. ``'{"1":"Single Plane"}'``
    - Compact CLI form, e.g. ``"1:Single Plane"`` or ``"1:Plane A,2:Plane B"``
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.startswith("{"):
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("plane_code_map JSON must be an object of code→meaning pairs.")
            return parse_plane_code_map(parsed)
        out: dict[int, str] = {}
        for part in text.split(","):
            code_text, sep, meaning = part.partition(":")
            if not sep:
                raise ValueError(
                    "plane_code_map entries must look like '1:Single Plane' or "
                    "'1:Plane A,2:Plane B'."
                )
            out[int(code_text.strip())] = meaning.strip()
        return _validated_plane_code_map(out)
    if isinstance(raw, dict):
        return _validated_plane_code_map({int(k): str(v).strip() for k, v in raw.items()})
    raise ValueError("plane_code_map must be a dict, JSON object string, or 'code:meaning' list.")


def _validated_plane_code_map(mapping: dict[int, str]) -> dict[int, str]:
    if not mapping:
        return {}
    invalid = sorted({meaning for meaning in mapping.values() if meaning not in DOSETRACK_PLANE_MEANINGS})
    if invalid:
        raise ValueError(
            "plane_code_map meanings must be one of "
            f"{sorted(DOSETRACK_PLANE_MEANINGS)}; got {invalid}."
        )
    return mapping
