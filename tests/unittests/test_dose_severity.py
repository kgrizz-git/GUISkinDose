"""Unit tests for the pure peak-skin-dose severity band logic.

These live under ``tests/unittests/`` because ``guiskindose.gui.dose_severity``
imports ``nicegui`` under ``TYPE_CHECKING`` only, so the band functions are
importable in the core CI matrix that installs no ``gui`` extra.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from guiskindose.gui.dose_severity import (
    _ALL_TEXT_CLASSES,
    PSD_BAND_ELEVATED_MGY,
    PSD_BAND_HIGH_MGY,
    PSD_PENDING_TEXT,
    apply_psd_band,
    psd_band,
    psd_band_copy_key,
    psd_band_icon,
    psd_text_class,
    reset_psd_label,
)


class _FakeElement:
    """Minimal stand-in for a NiceGUI element's ``classes(remove=…, add=…)``."""

    def __init__(self) -> None:
        self.current: set[str] = set()

    def classes(self, *, remove: str | None = None, add: str | None = None) -> _FakeElement:
        if remove:
            self.current -= set(remove.split())
        if add:
            self.current |= set(add.split())
        return self

    def severity_classes(self) -> set[str]:
        return {name for name in self.current if name.startswith("text-dose-")}


@pytest.mark.parametrize(
    ("psd", "expected"),
    [
        (None, "pending"),
        (math.nan, "pending"),
        (math.inf, "pending"),
        (0.0, "low"),
        (-1.0, "low"),
        (4999.99, "low"),
        (5000.0, "elevated"),
        (9999.99, "elevated"),
        (10000.0, "high"),
        (10000.01, "high"),
        (1e9, "high"),
    ],
)
def test_psd_band_edges(psd: float | None, expected: str) -> None:
    assert psd_band(psd) == expected


def test_psd_band_treats_non_numeric_as_pending() -> None:
    assert psd_band("not a number") == "pending"  # type: ignore[arg-type]


def test_psd_band_derived_helpers_follow_the_band() -> None:
    assert psd_text_class(0.0) == "text-dose-low"
    assert psd_band_icon(None) == ""
    assert psd_band_icon(1e9) == "error"
    assert psd_band_copy_key(PSD_BAND_ELEVATED_MGY) == "results.psd_band.elevated"
    assert psd_band_copy_key(PSD_BAND_HIGH_MGY) == "results.psd_band.high"


def test_apply_psd_band_leaves_exactly_one_class_when_rebanded() -> None:
    element = _FakeElement()
    element.classes(add="text-h6 font-bold")

    apply_psd_band(cast(Any, element), 1.0)
    apply_psd_band(cast(Any, element), 12_000.0)

    assert element.severity_classes() == {"text-dose-high"}
    assert element.current == {"text-h6", "font-bold", "text-dose-high"}


def test_apply_psd_band_removes_the_whole_family() -> None:
    element = _FakeElement()
    element.current = set(_ALL_TEXT_CLASSES.split())

    apply_psd_band(cast(Any, element), 6_000.0)

    assert element.severity_classes() == {"text-dose-elevated"}


def test_reset_psd_label_shows_a_dash_and_the_pending_band() -> None:
    """`0.00 mGy` before a run reads as a real measurement of zero; `—` does not."""

    class _FakeLabel(_FakeElement):
        def __init__(self) -> None:
            super().__init__()
            self.text = "PSD: 9.50 mGy"
            self.current = {"text-dose-low"}

        def set_text(self, text: str) -> None:
            self.text = text

    label = _FakeLabel()

    reset_psd_label(cast(Any, label))

    assert label.text == PSD_PENDING_TEXT == "PSD: —"
    assert label.severity_classes() == {"text-dose-pending"}
