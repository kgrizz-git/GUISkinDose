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
    PsdReadout,
    apply_psd_band,
    apply_psd_presentation,
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


class _FakeTextElement(_FakeElement):
    """Fake label / icon: tracks text and the material symbol name."""

    def __init__(self, text: str = "", name: str = "") -> None:
        super().__init__()
        self.text = text
        self.name = name
        self.visible = True

    def set_text(self, text: str) -> None:
        self.text = text

    def set_name(self, name: str) -> None:
        self.name = name

    def set_visibility(self, visible: bool) -> None:
        self.visible = visible


def _fake_readout() -> Any:
    """A ``PsdReadout`` of fakes — no NiceGUI needed, so this stays pure."""
    return PsdReadout(
        row=cast(Any, _FakeElement()),
        icon=cast(Any, _FakeTextElement(name="")),
        value=cast(Any, _FakeTextElement(text="PSD: 9.50 mGy")),
        tooltip=cast(Any, _FakeTextElement(text="")),
    )


def test_reset_psd_label_shows_a_dash_and_the_pending_band() -> None:
    """`0.00 mGy` before a run reads as a real measurement of zero; `—` does not."""
    readout = _fake_readout()

    reset_psd_label(readout)

    assert readout.value.text == PSD_PENDING_TEXT == "PSD: —"
    assert readout.value.severity_classes() == {"text-dose-pending"}


def test_reset_psd_label_clears_the_icon_and_the_tooltip() -> None:
    """A stale High icon and tooltip next to a pending dash would contradict it."""
    readout = _fake_readout()
    apply_psd_presentation(readout, 12_000.0)

    reset_psd_label(readout)

    assert readout.icon.name == ""
    assert readout.icon.visible is False
    assert readout.icon.severity_classes() == {"text-dose-pending"}
    assert readout.tooltip.text == "Not calculated yet"


@pytest.mark.parametrize(
    ("psd", "icon", "visible", "tooltip"),
    [
        (None, "", False, "Not calculated yet"),
        (0.0, "check_circle", True, "Low — peak skin dose below 5000 mGy"),
        (4999.0, "check_circle", True, "Low — peak skin dose below 5000 mGy"),
        (
            5000.0,
            "warning",
            True,
            "Elevated — peak skin dose 5000 to just under 10000 mGy",
        ),
        (
            10_000.0,
            "error",
            True,
            "High — peak skin dose 10000 mGy or above",
        ),
    ],
)
def test_apply_psd_presentation_moves_all_three_carriers(
    psd: float | None, icon: str, visible: bool, tooltip: str
) -> None:
    """The band edges are pinned here too: the tooltip must name the band the
    colour is actually showing, at exactly 5000 and exactly 10000 mGy. Saying
    High means "above 10000" would contradict a High colour at exactly 10000.
    """
    readout = _fake_readout()

    apply_psd_presentation(readout, psd)

    assert readout.icon.name == icon
    assert readout.icon.visible is visible
    assert readout.tooltip.text == tooltip
    assert readout.value.severity_classes() == {psd_text_class(psd)}


def test_apply_psd_presentation_leaves_one_band_when_repeated() -> None:
    readout = _fake_readout()

    apply_psd_presentation(readout, 1.0)
    apply_psd_presentation(readout, 6_000.0)
    apply_psd_presentation(readout, 1.0)

    assert readout.value.severity_classes() == {"text-dose-low"}
    assert readout.icon.severity_classes() == {"text-dose-low"}
