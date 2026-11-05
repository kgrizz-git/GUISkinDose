"""Tests for packaging/portable/selfcheck.py pure helper functions."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_PORTABLE = Path(__file__).resolve().parents[2] / "packaging" / "portable"


@pytest.fixture(scope="module")
def selfcheck() -> Any:
    sys.path.insert(0, str(_PORTABLE))
    try:
        yield importlib.import_module("selfcheck")
    finally:
        sys.path.remove(str(_PORTABLE))


def test_require_preview_stem(selfcheck: Any) -> None:
    selfcheck._require_preview_stem("adult_male_reduced_3000t")
    with pytest.raises(ValueError, match="edition_phantom_payload_wrong"):
        selfcheck._require_preview_stem("adult_male")
    with pytest.raises(ValueError, match="edition_phantom_payload_wrong"):
        selfcheck._require_preview_stem("adult_male_reduced_1000t")
