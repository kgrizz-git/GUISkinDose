"""Helpers for DoseTrack / CID 10003 plane-code maps."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from guiskindose.constants import DOSETRACK_PLANE_MEANINGS

# Decimal integer only (optional sign). Rejects underscores, hex, and floats.
_PLANE_CODE_RE = re.compile(r"[+-]?\d+$")


def _parse_plane_code(code: object) -> int:
    """Parse a plane-map key as a decimal integer with a clear ValueError on failure."""
    text = str(code).strip()
    if not _PLANE_CODE_RE.fullmatch(text):
        raise ValueError(
            f"plane_code_map code must be a decimal integer, got {code!r}."
        )
    return int(text)


def _plane_map_from_json_pairs(pairs: Sequence[tuple[object, object]]) -> dict[int, str]:
    """``json.loads`` object_pairs_hook for flat plane-code maps.

    Rejects duplicate JSON member names (default ``json.loads`` would keep only
    the last value) and duplicate integer codes (``"1"`` vs ``"01"``) via
    :func:`_mapping_from_pairs` before returning the validated map.
    """
    seen_names: dict[object, object] = {}
    typed_pairs: list[tuple[int, str]] = []
    for key, value in pairs:
        if key in seen_names:
            raise ValueError(
                f"plane_code_map JSON has duplicate member name {key!r} "
                f"(conflicting values {seen_names[key]!r} and {value!r})."
            )
        seen_names[key] = value
        typed_pairs.append((_parse_plane_code(key), str(value).strip()))
    return _validated_plane_code_map(_mapping_from_pairs(typed_pairs))


def parse_plane_code_map(raw: object) -> dict[int, str] | None:
    """Parse an explicit DoseTrack plane-code map from settings or CLI text.

    Accepts:
    - ``None`` / empty → ``None``
    - ``dict`` with int-like keys and meaning values (``"Plane A"`` / ``"Plane B"`` /
      ``"Single Plane"``)
    - JSON object string, e.g. ``'{"1":"Single Plane"}'``
    - Compact CLI form, e.g. ``"1:Single Plane"`` or ``"1:Plane A,2:Plane B"``

    Duplicate integer codes (including alternate spellings such as ``"1"`` and
    ``"01"``) are rejected — later entries must not silently overwrite earlier
    meanings. Duplicate JSON object member names are also rejected (``json.loads``
    would otherwise keep only the last value).
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        if text.startswith("{"):
            parsed = json.loads(text, object_pairs_hook=_plane_map_from_json_pairs)
            if not isinstance(parsed, dict):
                raise ValueError("plane_code_map JSON must be an object of code→meaning pairs.")
            return parsed
        pairs: list[tuple[int, str]] = []
        for part in text.split(","):
            code_text, sep, meaning = part.partition(":")
            if not sep:
                raise ValueError(
                    "plane_code_map entries must look like '1:Single Plane' or "
                    "'1:Plane A,2:Plane B'."
                )
            pairs.append((_parse_plane_code(code_text), meaning.strip()))
        return _validated_plane_code_map(_mapping_from_pairs(pairs))
    if isinstance(raw, dict):
        pairs = [(_parse_plane_code(k), str(v).strip()) for k, v in raw.items()]
        return _validated_plane_code_map(_mapping_from_pairs(pairs))
    raise ValueError("plane_code_map must be a dict, JSON object string, or 'code:meaning' list.")


def _mapping_from_pairs(pairs: list[tuple[int, str]]) -> dict[int, str]:
    """Build a code→meaning dict, rejecting duplicate integer codes."""
    out: dict[int, str] = {}
    for code, meaning in pairs:
        if code in out:
            raise ValueError(
                f"plane_code_map has duplicate plane code {code} "
                f"(conflicting meanings {out[code]!r} and {meaning!r})."
            )
        out[code] = meaning
    return out


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
