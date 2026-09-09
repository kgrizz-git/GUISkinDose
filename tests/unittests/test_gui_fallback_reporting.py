"""Tests for unmatched-model fallback reporting (Plan §4)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from guiskindose.constants import KEY_RDSR_MANUFACTURER, KEY_RDSR_MANUFACTURER_MODEL_NAME
from guiskindose.gui.exam_loaders import _build_exam_meta_entry
from guiskindose.gui.geometry_preview import geometry_vendor_notice
from guiskindose.gui.settings_builder import (
    fallback_normalization_exam_count,
    format_input_scanner_label,
    format_normalization_profile_label,
    refresh_normalization_warnings,
)
from guiskindose.gui.state import AppState
from guiskindose.settings.normalization_settings import NormalizationSettings


def _make_meta(**overrides: object) -> dict:
    base: dict = {
        "normalization_method": "Fallback",
        "input_manufacturer": "ACME Medical",
        "input_model": "Xray 9000",
        "manufacturer": "Default",
        "model": "Default",
        "schema": "dicom_rdsr",
        "source_type": "dicom",
        "warnings": [],
    }
    base.update(overrides)
    return base


def _norm_settings_with_default() -> NormalizationSettings:
    """NormalizationSettings containing only a Default profile."""
    return NormalizationSettings(
        normalization_settings=[
            {
                "manufacturer": "Default",
                "models": ["Default"],
                "translation_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                "translation_direction": {"x": "+", "y": "+", "z": "+"},
                "rotation_direction": {
                    "Ap1": "+",
                    "Ap2": "+",
                    "Ap3": "+",
                    "At1": "+",
                    "At2": "+",
                    "At3": "+",
                },
                "field_size_mode": "CFA",
                "detector_side_length": 40,
            }
        ]
    )


def test_fallback_notice_names_actual_unmatched_scanner() -> None:
    """Geometry notice must name the actual input model, not 'Default'."""
    notice = geometry_vendor_notice(_make_meta())
    assert "ACME Medical / Xray 9000" in notice
    assert "Default normalization in use" in notice


def test_fallback_notice_uses_input_over_matched_profile() -> None:
    """Prefer input_manufacturer/input_model over matched manufacturer/model."""
    notice = geometry_vendor_notice(
        _make_meta(input_manufacturer="FooCorp", input_model="Bar1"),
        manufacturer="Default",
        model="Default",
    )
    assert "FooCorp / Bar1" in notice
    assert "Default" not in notice.split("Default normalization")[0]


def test_active_exam_summary_shows_input_identity_for_fallback() -> None:
    """Active exam summary should show the actual input scanner identity."""
    meta = _make_meta()
    summary = geometry_vendor_notice(meta)
    assert "Active exam: ACME Medical / Xray 9000" in summary
    assert "Fallback" in summary


def test_multi_exam_fallback_warning_counts_attr_per_exam() -> None:
    """Per-exam meta must carry its own input identity; count uses production helper."""
    meta1 = _make_meta(input_manufacturer="VendorA", input_model="ModelA", normalization_method="Fallback")
    meta2 = _make_meta(input_manufacturer="VendorB", input_model="ModelB", normalization_method="Matched")
    meta3 = _make_meta(input_manufacturer="VendorC", input_model="ModelC", normalization_method="Fallback")
    st = AppState()
    st.loaded_exam_meta = [meta1, meta2, meta3]
    st.loaded_exams = [SimpleNamespace() for _ in range(3)]
    st.is_multi_exam = True

    assert fallback_normalization_exam_count(st) == 2
    refresh_normalization_warnings(st)
    assert len(st.normalization_warnings) == 2
    assert "Exam 1: Scanner 'VendorA ModelA'" in st.normalization_warnings[0]
    assert "Exam 3: Scanner 'VendorC ModelC'" in st.normalization_warnings[1]


def test_update_used_settings_retains_input_identity_on_fallback() -> None:
    """NormalizationSettings must keep raw input identity when matching Default."""
    norm = _norm_settings_with_default()
    data = pd.DataFrame(
        {
            KEY_RDSR_MANUFACTURER: ["ACME Medical"],
            KEY_RDSR_MANUFACTURER_MODEL_NAME: ["Xray 9000"],
        }
    )
    norm.update_used_settings(data)
    assert norm.normalization_method == "Fallback"
    assert norm.input_manufacturer == "ACME Medical"
    assert norm.input_model == "Xray 9000"
    assert norm.matched_manufacturer == "Default"


def test_format_input_scanner_label_prefers_input_identity() -> None:
    st = AppState()
    st.manufacturer = "Default"
    st.model = "Default"
    st.input_manufacturer = "ACME"
    st.input_model = "Xray 9000"
    assert format_input_scanner_label(st) == "ACME Xray 9000"


def test_format_normalization_profile_label_matched_and_fallback() -> None:
    st = AppState()
    st.normalization_method = "Matched"
    st.manufacturer = "Siemens"
    st.model = "AXIOM-Artis"
    assert format_normalization_profile_label(st) == "Matched: Siemens AXIOM-Artis"
    st.normalization_method = "Fallback"
    assert format_normalization_profile_label(st) == "Default profile"


def test_fallback_notice_omits_input_when_absent() -> None:
    """Notice should still say 'Default normalization' when input identity is missing."""
    meta = _make_meta(input_manufacturer="", input_model="")
    notice = geometry_vendor_notice(meta)
    assert "Default normalization in use" in notice


def test_matched_profile_does_not_show_fallback_warning() -> None:
    """Matched normalization should not produce a fallback warning."""
    meta = _make_meta(normalization_method="Matched")
    notice = geometry_vendor_notice(meta)
    assert "Default normalization in use" not in notice


def test_build_exam_meta_entry_sets_empty_input_identity_for_tabular() -> None:
    """Tabular meta construction must leave input identity empty."""
    st = AppState()
    meta = _build_exam_meta_entry(
        st,
        Path("events.csv"),
        "dosetrack",
        pd.DataFrame(),
        SimpleNamespace(schema_name="dosetrack"),
        [],
        {
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
            "flip_tx": False,
            "flip_ty": False,
            "flip_tz": False,
        },
        0.0,
        0.0,
        0.0,
    )
    assert meta["normalization_method"] == "Tabular"
    assert meta["input_manufacturer"] == ""
    assert meta["input_model"] == ""
