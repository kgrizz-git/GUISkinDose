"""Tests for pure GUI summary formatters."""

from __future__ import annotations

from guiskindose.gui.summary_formatters import format_scale_cm_label


def test_format_scale_cm_label_includes_scaled_centimeters() -> None:
    assert format_scale_cm_label(1.25, 100.0) == "1.25x  (125.0 cm)"


def test_format_scale_cm_label_uses_dash_for_zero_extent() -> None:
    assert format_scale_cm_label(0.85, 0.0) == "0.85x  (—)"
