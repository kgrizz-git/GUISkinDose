"""Focused tests for additive tube-identity fields (Plan 1 Chunk 3).

Covers:
  * CID 10003 recognition in parser, normalizer, kerma, and DoseTrack adapter.
  * Canonical identity is additive and never rewrites the legacy
    ``acquisition_plane`` column that ``corrections._match_device_rows``
    compares verbatim.
  * Unknown / non-CID values return ``unknown`` and never silently match a
    real single-plane calibration.
  * DoseTrack unknown integer codes raise ``ValueError`` (1-2 codes) or keep
    the existing hard error (3+ codes).
  * k_tab lookup results are unchanged by the presence of canonical columns.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL,
    KEY_NORMALIZATION_ACQUISITION_PLANE_CODE,
    KEY_NORMALIZATION_ACQUISITION_PLANE_CODING_SCHEME,
    KEY_NORMALIZATION_ACQUISITION_PLANE_MEANING,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_KVP,
    KEY_NORMALIZATION_MODEL_NAME,
    KEY_NORMALIZATION_STATION_NAME,
)
from guiskindose.kerma_correction import (
    normalize_tube,
    resolve_canonical_plane_identity,
    resolve_correction_factors,
)
from guiskindose.rdsr_normalizer import _normalize_machine_parameters
from guiskindose.settings.normalization_settings import NormalizationSettings
from guiskindose.settings.rotation_direction import RotationDirection
from guiskindose.settings.translation_direction import TranslationDirection
from guiskindose.settings.translation_offset import TranslationOffset

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_settings() -> NormalizationSettings:
    """Return a minimal NormalizationSettings for unit tests."""
    s = NormalizationSettings(normalization_settings=[])
    s.trans_offset = TranslationOffset()
    s.trans_dir = TranslationDirection()
    s.rot_dir = RotationDirection()
    s.field_size_mode = "CFA"
    s.detector_side_length = "0"
    return s


def _capture_warnings(func, *args, **kwargs):
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        result = func(*args, **kwargs)
    finally:
        logger.removeHandler(handler)
    return result, messages


def _default_settings():
    from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS

    from guiskindose.settings import PyskindoseSettings
    return PyskindoseSettings(DEVELOPMENT_PARAMETERS)


# ---------------------------------------------------------------------------
# 1. normalize_tube / resolve_canonical_plane_identity
# ---------------------------------------------------------------------------

class TestNormalizeTube:
    def test_known_aliases(self):
        assert normalize_tube("Single Plane") == "single"
        assert normalize_tube("Plane A") == "A"
        assert normalize_tube("Plane B") == "B"
        assert normalize_tube("plane a") == "A"
        assert normalize_tube("plane b") == "B"

    def test_none_and_empty_and_nan_return_unknown(self):
        assert normalize_tube(None) == "unknown"
        assert normalize_tube("") == "unknown"
        assert normalize_tube(float("nan")) == "unknown"

    def test_unrecognized_text_returns_unknown(self):
        assert normalize_tube("Biplane") == "unknown"
        assert normalize_tube("Siemens Custom") == "unknown"


class TestResolveCanonicalPlaneIdentity:
    def test_cid_10003_strings(self):
        assert resolve_canonical_plane_identity("113620") == "A"
        assert resolve_canonical_plane_identity("113621") == "B"
        assert resolve_canonical_plane_identity("113622") == "single"

    def test_unknown_code_returns_unknown(self):
        assert resolve_canonical_plane_identity("999999") == "unknown"
        assert resolve_canonical_plane_identity(None) == "unknown"
        assert resolve_canonical_plane_identity(float("nan")) == "unknown"

    def test_integer_codes(self):
        assert resolve_canonical_plane_identity(113620) == "A"
        assert resolve_canonical_plane_identity(113621) == "B"
        assert resolve_canonical_plane_identity(113622) == "single"

    def test_float_string_and_invalid_tokens_return_unknown_or_canonical(self):
        assert resolve_canonical_plane_identity("113620.0") == "A"
        assert resolve_canonical_plane_identity("not-a-code") == "unknown"
        assert resolve_canonical_plane_identity(object()) == "unknown"


# ---------------------------------------------------------------------------
# 2. kerma resolution: unknown tube must not match a real calibration
# ---------------------------------------------------------------------------

class TestUnknownTubeResolution:
    def test_unknown_tube_misses_table_uses_default_factor(self):
        df = pd.DataFrame(
            {
                KEY_NORMALIZATION_STATION_NAME: ["unit-01"],
                KEY_NORMALIZATION_ACQUISITION_PLANE: ["Biplane"],
            }
        )
        table = {("unit-01", "single"): 1.05, ("unit-01", "A"): 0.97}
        result = resolve_correction_factors(df, table, default_factor=1.0)
        assert result.factors == [1.0]
        # Unknown tube is unresolved identity, not a table miss for a known tube.
        assert result.unresolved_event_indices == [0]
        assert result.table_miss_event_indices == []

    def test_unknown_tube_does_not_leak_in_warnings(self, caplog):
        df = pd.DataFrame(
            {
                KEY_NORMALIZATION_STATION_NAME: ["unit-01"],
                KEY_NORMALIZATION_ACQUISITION_PLANE: ["Unknown Plane"],
            }
        )
        result = resolve_correction_factors(df, {}, default_factor=1.0)
        assert result.unresolved_event_indices == [0]
        warn_text = " ".join(r.message for r in caplog.records if r.levelname == "WARNING")
        assert "Unknown Plane" not in warn_text

    def test_unknown_tube_never_matches_unknown_table_key(self):
        """A CF table row keyed as tube=unknown must not apply to ambiguous events."""
        df = pd.DataFrame(
            {
                KEY_NORMALIZATION_STATION_NAME: ["unit-01"],
                KEY_NORMALIZATION_ACQUISITION_PLANE: ["Biplane"],
            }
        )
        table = {("unit-01", "unknown"): 9.99}
        result = resolve_correction_factors(df, table, default_factor=1.0)
        assert result.factors == [1.0]
        assert result.unresolved_event_indices == [0]


# ---------------------------------------------------------------------------
# 3. Normalizer additive fields
# ---------------------------------------------------------------------------

class TestNormalizerAdditivePlaneFields:
    def test_dicom_code_value_populates_additive_columns(self):
        data_parsed = pd.DataFrame(
            {
                "AcquisitionPlane": ["Plane A", "Single Plane"],
                "AcquisitionPlane_CodeValue": ["113620", "113622"],
                "AcquisitionPlane_CodingSchemeDesignator": ["DCM", "DCM"],
                "Manufacturer": ["Siemens", "Siemens"],
                "ManufacturerModelName": ["AXIOM-Artis", "AXIOM-Artis"],
                "DistanceSourcetoDetector_mm": [1000.0, 1000.0],
                "DistanceSourcetoIsocenter_mm": [750.0, 750.0],
                "IrradiationEventType": ["Fluoroscopy", "Fluoroscopy"],
            }
        )
        data_norm = pd.DataFrame()
        data_norm = _normalize_machine_parameters(
            data_parsed, data_norm, _norm_settings()
        )

        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE].tolist() == [
            "Plane A",
            "Single Plane",
        ]
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CODE].tolist() == [
            "113620",
            "113622",
        ]
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CODING_SCHEME].tolist() == [
            "DCM",
            "DCM",
        ]
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_MEANING].tolist() == [
            "Plane A",
            "Single Plane",
        ]
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL].tolist() == [
            "A",
            "single",
        ]

    def test_missing_code_value_yields_unknown_canonical(self):
        data_parsed = pd.DataFrame(
            {
                "AcquisitionPlane": ["Plane A", "Single Plane"],
                "Manufacturer": ["Siemens", "Siemens"],
                "ManufacturerModelName": ["AXIOM-Artis", "AXIOM-Artis"],
                "DistanceSourcetoDetector_mm": [1000.0, 1000.0],
                "DistanceSourcetoIsocenter_mm": [750.0, 750.0],
                "IrradiationEventType": ["Fluoroscopy", "Fluoroscopy"],
            }
        )
        data_norm = pd.DataFrame()
        data_norm = _normalize_machine_parameters(
            data_parsed, data_norm, _norm_settings()
        )
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL].tolist() == [
            "unknown",
            "unknown",
        ]

    def test_non_cid_code_value_yields_unknown_canonical(self):
        data_parsed = pd.DataFrame(
            {
                "AcquisitionPlane": ["Custom Plane"],
                "AcquisitionPlane_CodeValue": ["999999"],
                "AcquisitionPlane_CodingSchemeDesignator": ["DCM"],
                "Manufacturer": ["Siemens"],
                "ManufacturerModelName": ["AXIOM-Artis"],
                "DistanceSourcetoDetector_mm": [1000.0],
                "DistanceSourcetoIsocenter_mm": [750.0],
                "IrradiationEventType": ["Fluoroscopy"],
            }
        )
        data_norm = pd.DataFrame()
        data_norm = _normalize_machine_parameters(
            data_parsed, data_norm, _norm_settings()
        )
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL].iloc[0] == "unknown"

    def test_non_dcm_code_scheme_yields_unknown_without_meaning_fallback(self):
        """Non-DCM CodeValue rows must stay unknown even when meaning looks valid."""
        data_parsed = pd.DataFrame(
            {
                "AcquisitionPlane": ["Plane A"],
                "AcquisitionPlane_CodeValue": ["113620"],
                "AcquisitionPlane_CodingSchemeDesignator": ["99LOCAL"],
                "Manufacturer": ["Siemens"],
                "ManufacturerModelName": ["AXIOM-Artis"],
                "DistanceSourcetoDetector_mm": [1000.0],
                "DistanceSourcetoIsocenter_mm": [750.0],
                "IrradiationEventType": ["Fluoroscopy"],
            }
        )
        data_norm = pd.DataFrame()
        data_norm = _normalize_machine_parameters(
            data_parsed, data_norm, _norm_settings()
        )
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE].iloc[0] == "Plane A"
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL].iloc[0] == "unknown"

    def test_code_value_without_scheme_yields_unknown(self):
        data_parsed = pd.DataFrame(
            {
                "AcquisitionPlane": ["Plane A"],
                "AcquisitionPlane_CodeValue": ["113620"],
                "Manufacturer": ["Siemens"],
                "ManufacturerModelName": ["AXIOM-Artis"],
                "DistanceSourcetoDetector_mm": [1000.0],
                "DistanceSourcetoIsocenter_mm": [750.0],
                "IrradiationEventType": ["Fluoroscopy"],
            }
        )
        data_norm = pd.DataFrame()
        data_norm = _normalize_machine_parameters(
            data_parsed, data_norm, _norm_settings()
        )
        assert data_norm[KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL].iloc[0] == "unknown"


# ---------------------------------------------------------------------------
# 4. DoseTrack plane-code normalization
# ---------------------------------------------------------------------------

class TestDoseTrackPlaneCodeNormalization:
    def test_cid_backed_codes_map_correctly(self):
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([113620, 113621, 113622])
        result = _normalize_plane_code(series)
        assert result.tolist() == ["Plane A", "Plane B", "Single Plane"]

    def test_single_cid_code_maps(self):
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([113622])
        result = _normalize_plane_code(series)
        assert result.tolist() == ["Single Plane"]

    def test_one_unknown_integer_raises_value_error(self):
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([1])
        with pytest.raises(ValueError, match="non-CID-10003"):
            _normalize_plane_code(series)

    def test_two_unknown_integers_raises_value_error(self):
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([1, 2])
        with pytest.raises(ValueError, match="non-CID-10003"):
            _normalize_plane_code(series)

    def test_three_distinct_integers_raises_value_error(self):
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([1, 2, 3])
        with pytest.raises(ValueError, match=r"expected 1 .* or 2|plane_code_map"):
            _normalize_plane_code(series)

    def test_three_codes_succeed_with_complete_explicit_map(self):
        from guiskindose.input_adapters.base import AdapterContext
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([1, 2, 3])
        ctx = AdapterContext(
            column_map={},
            raw_headers=[],
            settings=None,
            warnings=[],
            plane_code_map={1: "Plane A", 2: "Plane B", 3: "Single Plane"},
        )
        result = _normalize_plane_code(series, ctx=ctx)
        assert result.tolist() == ["Plane A", "Plane B", "Single Plane"]

    def test_explicit_map_overrides_unknown(self):
        from guiskindose.input_adapters.base import AdapterContext
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series([1, 2])
        ctx = AdapterContext(
            column_map={},
            raw_headers=[],
            settings=None,
            warnings=[],
            plane_code_map={1: "Plane A", 2: "Plane B"},
        )
        result = _normalize_plane_code(series, ctx=ctx)
        assert result.tolist() == ["Plane A", "Plane B"]

    def test_string_codes_bypass_integer_path(self):
        from guiskindose.input_adapters.dosetrack import _normalize_plane_code

        series = pd.Series(["Single Plane", "Plane A"])
        result = _normalize_plane_code(series)
        assert result.tolist() == ["Single Plane", "Plane A"]

    def test_plane_code_map_rejects_duplicate_integer_codes(self):
        from guiskindose.input_adapters.plane_code_map import parse_plane_code_map

        with pytest.raises(ValueError, match="duplicate plane code"):
            parse_plane_code_map("1:Plane A,01:Plane B")
        with pytest.raises(ValueError, match="duplicate plane code"):
            parse_plane_code_map({"1": "Plane A", "01": "Plane B"})
        with pytest.raises(ValueError, match="duplicate plane code"):
            parse_plane_code_map('{"1":"Plane A","01":"Plane B"}')


# ---------------------------------------------------------------------------
# 5. DoseTrack integration: canonical identity through the adapter
# ---------------------------------------------------------------------------

class TestDoseTrackCanonicalIdentity:
    def test_cid_backed_single_plane_produces_canonical_single(self):
        from guiskindose.input_adapters.registry import read_and_normalize_input

        csv_text = (
            "Equipment Name,Plane Code,Air Kerma (mGy),Tube Voltage Peak (kV),"
            "Positioner Primary Angle (deg),Positioner Secondary Angle (deg),"
            "Distance Source to Detector (mm),Distance Source To Isocenter (mm),"
            "Table Longitudinal Position (mm),Table Lateral Position (mm),"
            "Table Height Position (mm),Collimated Field Area (m2),"
            "Filter Material,Filter Thickness\n"
            "AXIOM-Artis,113622,15.0,70,0,0,1000,750,0,0,290,0.01,Cu,0.1\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_text)
            path = f.name

        try:
            result = read_and_normalize_input(
                Path(path), input_schema="dosetrack", settings=_default_settings()
            )
            assert result.normalized_data[
                KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL
            ].iloc[0] == "single"
            assert (
                result.normalized_data[KEY_NORMALIZATION_ACQUISITION_PLANE].iloc[0]
                == "Single Plane"
            )
        finally:
            Path(path).unlink()

    def test_unknown_plane_code_raises(self):
        from guiskindose.input_adapters.registry import read_and_normalize_input

        csv_text = (
            "Equipment Name,Plane Code,Air Kerma (mGy),Tube Voltage Peak (kV),"
            "Positioner Primary Angle (deg),Positioner Secondary Angle (deg),"
            "Distance Source to Detector (mm),Distance Source To Isocenter (mm),"
            "Table Longitudinal Position (mm),Table Lateral Position (mm),"
            "Table Height Position (mm),Collimated Field Area (m2),"
            "Filter Material,Filter Thickness\n"
            "AXIOM-Artis,1,15.0,70,0,0,1000,750,0,0,290,0.01,Cu,0.1\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_text)
            path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                read_and_normalize_input(
                    Path(path), input_schema="dosetrack", settings=_default_settings()
                )
            # The adapter wraps the inner ValueError; check the cause for the
            # specific non-CID-10003 message.
            assert exc_info.value.__cause__ is not None
            assert "non-CID-10003" in str(exc_info.value.__cause__)
        finally:
            Path(path).unlink()

    def test_explicit_map_via_settings_unblocks_legacy_codes(self):
        """Settings dosetrack_plane_code_map must reach AdapterContext."""
        from guiskindose.input_adapters.registry import read_and_normalize_input

        csv_text = (
            "Equipment Name,Plane Code,Air Kerma (mGy),Tube Voltage Peak (kV),"
            "Positioner Primary Angle (deg),Positioner Secondary Angle (deg),"
            "Distance Source to Detector (mm),Distance Source To Isocenter (mm),"
            "Table Longitudinal Position (mm),Table Lateral Position (mm),"
            "Table Height Position (mm),Collimated Field Area (m2),"
            "Filter Material,Filter Thickness\n"
            "AXIOM-Artis,1,15.0,70,0,0,1000,750,0,0,290,0.01,Cu,0.1\n"
        )
        settings = _default_settings()
        settings.dosetrack_plane_code_map = {1: "Single Plane"}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(csv_text)
            path = f.name
        try:
            result = read_and_normalize_input(
                Path(path), input_schema="dosetrack", settings=settings
            )
            assert result.normalized_data[KEY_NORMALIZATION_ACQUISITION_PLANE].iloc[0] == (
                "Single Plane"
            )
        finally:
            Path(path).unlink()


# ---------------------------------------------------------------------------
# 6. k_tab regression: canonical columns do not change k_tab
# ---------------------------------------------------------------------------

class TestKTabRegressionCanonicalFields:
    """Presence of additive canonical columns must not alter k_tab lookup."""

    def _db_path(self):
        repo_root = Path(__file__).resolve().parents[2]
        return str(repo_root / "corrections.db")

    def test_canonical_unknown_does_not_alter_k_tab(self):
        from guiskindose.corrections import calculate_k_tab

        data = pd.DataFrame(
            {
                KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane"],
                KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL: ["unknown"],
                KEY_NORMALIZATION_MODEL_NAME: ["AXIOM-Artis"],
                KEY_NORMALIZATION_KVP: [80.0],
                KEY_NORMALIZATION_FILTER_SIZE_COPPER: [0.3],
                KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [0.0],
            }
        )
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=self._db_path(),
            estimate_k_tab=False,
            k_tab_val=0.8,
        )
        assert result[0] == pytest.approx(0.7319, abs=1e-6)

    def test_canonical_single_does_not_alter_k_tab(self):
        from guiskindose.corrections import calculate_k_tab

        data = pd.DataFrame(
            {
                KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane"],
                KEY_NORMALIZATION_ACQUISITION_PLANE_CANONICAL: ["single"],
                KEY_NORMALIZATION_MODEL_NAME: ["AXIOM-Artis"],
                KEY_NORMALIZATION_KVP: [80.0],
                KEY_NORMALIZATION_FILTER_SIZE_COPPER: [0.3],
                KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [0.0],
            }
        )
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=self._db_path(),
            estimate_k_tab=False,
            k_tab_val=0.8,
        )
        assert result[0] == pytest.approx(0.7319, abs=1e-6)
