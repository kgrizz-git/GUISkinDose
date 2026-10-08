"""Full-frame characterization of ``rdsr_normalizer`` on every bundled example RDSR.

``test_rdsr_normalizer_characterization.py`` pins selected columns of the first
rows. This test pins *every* column of *every* row, as one digest per column, so
input-hardening changes (duplicate collapse, unit conversion, required-concept
checks) cannot silently move any normalized value on the bundled examples.

Floats are rounded to 9 significant digits before hashing, so the digests do not
depend on platform float formatting. A failure names the changed columns.

Regenerate deliberately (and review the diff) with::

    GUISKINDOSE_REGEN_NORMALIZED_DIGESTS=1 uv run pytest tests/unittests/test_rdsr_normalizer_full_frame.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd
import pydicom
import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

_RDSR_DIR = get_path_to_example_rdsr_files()
_EXAMPLES = sorted(p.name for p in _RDSR_DIR.glob("*.dcm"))
_DIGESTS_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "rdsr_normalized_digests.json"
_REGEN_ENV = "GUISKINDOSE_REGEN_NORMALIZED_DIGESTS"


def _canonical(value: Any) -> str:
    """Return a platform-stable text form of one cell."""
    if value is None:
        return "None"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.9g}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    try:
        if pd.isna(value):
            return "nan"
    except (TypeError, ValueError):
        # Non-scalar values may not support a boolean missingness check; use the fallbacks below.
        pass
    if hasattr(value, "item"):
        return _canonical(value.item())
    return repr(value)


def _column_digests(frame: pd.DataFrame) -> dict[str, str]:
    digests = {}
    for column in frame.columns:
        text = "\n".join(_canonical(v) for v in frame[column].tolist())
        digests[str(column)] = hashlib.sha256(text.encode()).hexdigest()[:16]
    return digests


def _normalize(fname: str) -> pd.DataFrame:
    parsed = rdsr_parser(pydicom.dcmread(str(_RDSR_DIR / fname)), silence_pydicom_warnings=True)
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    settings = PyskindoseSettings(settings=base, output_format="dict")
    return rdsr_normalizer(parsed, settings=settings)


def _current() -> dict[str, dict]:
    result = {}
    for fname in _EXAMPLES:
        frame = _normalize(fname)
        result[fname] = {"rows": len(frame), "columns": _column_digests(frame)}
    return result


def test_regenerate_digests_when_requested() -> None:
    if not os.environ.get(_REGEN_ENV):
        pytest.skip(f"set {_REGEN_ENV}=1 to regenerate the digest file")
    _DIGESTS_PATH.write_text(json.dumps(_current(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_every_bundled_example_is_pinned() -> None:
    pinned = json.loads(_DIGESTS_PATH.read_text(encoding="utf-8"))
    assert sorted(pinned) == _EXAMPLES


@pytest.mark.parametrize("fname", _EXAMPLES)
def test_normalized_frame_is_unchanged(fname: str) -> None:
    pinned = json.loads(_DIGESTS_PATH.read_text(encoding="utf-8"))[fname]
    frame = _normalize(fname)
    current = _column_digests(frame)
    assert len(frame) == pinned["rows"]
    changed = sorted(c for c in set(current) | set(pinned["columns"]) if current.get(c) != pinned["columns"].get(c))
    assert not changed, f"{fname}: normalized columns changed: {changed}"
