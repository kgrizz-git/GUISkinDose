"""Tests for mypyskindose.input_adapters (Phase 1 — normalized schema)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabular_inputs"


# ── column_mapper ──────────────────────────────────────────────────────────────


class TestDetectHeaderRow:
    def _make_df(self, rows: list[list[str]]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_header_at_row_0(self):
        from mypyskindose.input_adapters.column_mapper import detect_header_row
        from mypyskindose.input_adapters.normalized import NORMALIZED_COLUMN_NAMES

        rows = [
            list(NORMALIZED_COLUMN_NAMES)[:5] + ["extra"],
            ["AXIOM-Artis", "107.1", "78.5", "28.6", "63.5", "x"],
        ]
        df = self._make_df(rows)
        assert detect_header_row(df, NORMALIZED_COLUMN_NAMES) == 0

    def test_header_at_row_2(self):
        from mypyskindose.input_adapters.column_mapper import detect_header_row
        from mypyskindose.input_adapters.normalized import NORMALIZED_COLUMN_NAMES

        header = list(NORMALIZED_COLUMN_NAMES)
        rows = [
            ["Export date: 2026-06-09"] + [""] * (len(header) - 1),
            ["Source: MyPySkinDose"] + [""] * (len(header) - 1),
            header,
            ["AXIOM-Artis"] + ["0.0"] * (len(header) - 1),
        ]
        df = self._make_df(rows)
        assert detect_header_row(df, NORMALIZED_COLUMN_NAMES) == 2

    def test_no_header_found_raises(self):
        from mypyskindose.input_adapters.column_mapper import detect_header_row

        df = pd.DataFrame([["1.0", "2.0", "3.0"], ["4.0", "5.0", "6.0"]])
        with pytest.raises(ValueError, match="Could not locate a header row"):
            detect_header_row(df, frozenset({"model", "dsd", "dsi", "kvp"}))

    def test_large_export_with_many_unmapped_columns(self):
        """A 100-column export where only 6 columns are known must still succeed."""
        from mypyskindose.input_adapters.column_mapper import detect_header_row

        known = frozenset({"model", "dsd", "dsi", "kvp", "k irp", "ap1"})
        # 94 unknown columns + 6 known
        header = list(known) + [f"unknown_{i}" for i in range(94)]
        data = [["human", "1000", "750", "70", "0.1", "5"] + ["0"] * 94]
        df = pd.DataFrame([header, *data])
        # default min_score=5: 6 hits ≥ 5 → row 0 detected
        idx = detect_header_row(df, known)
        assert idx == 0


class TestMapColumns:
    def test_word_boundary_prevents_dap_to_tube_a_collision(self):
        """'Dose Area Product' must map to total dose, NOT to reference_dose_a."""
        from mypyskindose.input_adapters.column_mapper import COLUMN_PATTERNS, map_columns

        column_map, warnings = map_columns(["Dose Area Product", "Dose A"], COLUMN_PATTERNS)
        assert column_map.get("Dose Area Product") == "reference_dose_total"
        assert column_map.get("Dose A") == "reference_dose_a"
        assert not warnings

    def test_best_match_picks_longest_pattern(self):
        from mypyskindose.input_adapters.column_mapper import COLUMN_PATTERNS, map_columns

        column_map, _ = map_columns(["Reference Dose A"], COLUMN_PATTERNS)
        assert column_map.get("Reference Dose A") == "reference_dose_a"

    def test_bare_kv_not_matched(self):
        from mypyskindose.input_adapters.column_mapper import COLUMN_PATTERNS, map_columns

        column_map, _ = map_columns(["kv filter"], COLUMN_PATTERNS)
        assert "kv filter" not in column_map

    def test_kvp_matched(self):
        from mypyskindose.input_adapters.column_mapper import COLUMN_PATTERNS, map_columns

        column_map, _ = map_columns(["kVp"], COLUMN_PATTERNS)
        assert column_map.get("kVp") == "kvp"

    def test_tie_skipped_with_warning(self):
        from mypyskindose.input_adapters.column_mapper import map_columns

        # Craft patterns where one column matches two vars equally
        patterns = {"var_a": ["foo"], "var_b": ["foo"]}
        column_map, warnings = map_columns(["foo col"], patterns)
        assert "foo col" not in column_map
        assert any("multiple variables" in w for w in warnings)


class TestCheckDuplicateMappings:
    def test_duplicate_detected(self):
        from mypyskindose.input_adapters.column_mapper import check_duplicate_mappings

        column_map = {"Col A": "kvp", "Col B": "kvp", "Col C": "model"}
        errors = check_duplicate_mappings(column_map)
        assert len(errors) == 1
        assert "kvp" in errors[0]

    def test_no_duplicates(self):
        from mypyskindose.input_adapters.column_mapper import check_duplicate_mappings

        column_map = {"Col A": "kvp", "Col B": "model"}
        assert check_duplicate_mappings(column_map) == []


# ── tabular_loader ─────────────────────────────────────────────────────────────


class TestTabularLoader:
    def test_read_csv_comma(self):
        from mypyskindose.input_adapters.tabular_loader import read_csv

        result = read_csv(FIXTURES / "normalized_events.csv")
        assert result.delimiter == ","
        assert "utf" in result.encoding.lower()
        assert len(result.raw_df) == 3  # header + 2 data rows

    def test_read_tsv(self):
        from mypyskindose.input_adapters.tabular_loader import read_tsv

        result = read_tsv(FIXTURES / "normalized_events.tsv")
        assert result.delimiter == "\t"
        assert len(result.raw_df) == 3

    def test_read_excel(self):
        from mypyskindose.input_adapters.tabular_loader import read_excel

        result = read_excel(FIXTURES / "normalized_events.xlsx")
        assert result.delimiter is None
        assert len(result.raw_df) == 3  # header + 2 data rows

    def test_read_semicolon_csv(self):
        from mypyskindose.input_adapters.tabular_loader import read_csv

        result = read_csv(FIXTURES / "normalized_events_semicolon_decimalcomma.csv")
        assert result.delimiter == ";"

    def test_unsupported_suffix_raises(self):
        from mypyskindose.input_adapters.tabular_loader import load

        with pytest.raises(ValueError, match="Unsupported file suffix"):
            load(Path("data.xyz"))

    def test_read_excel_metadata_header(self):
        from mypyskindose.input_adapters.tabular_loader import read_excel

        result = read_excel(FIXTURES / "normalized_events_metadata_header.xlsx")
        assert len(result.raw_df) == 5  # 2 metadata + header + 2 data


# ── normalized adapter ────────────────────────────────────────────────────────


class TestNormalizedAdapter:
    def _load_and_adapt(self, filename: str):
        from mypyskindose.input_adapters import normalized as adapter
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.tabular_loader import load

        loaded = load(FIXTURES / filename)
        result = adapter.adapt(loaded, original_filename=filename)
        assert isinstance(result, InputAdapterResult), (
            f"Expected single InputAdapterResult for {filename!r}, got list"
        )
        return result

    def test_csv_round_trip(self):
        result = self._load_and_adapt("normalized_events.csv")
        assert len(result.normalized_data) == 2
        assert "model" in result.normalized_data.columns
        assert "kVp" in result.normalized_data.columns

    def test_tsv_round_trip(self):
        result = self._load_and_adapt("normalized_events.tsv")
        assert len(result.normalized_data) == 2

    def test_xlsx_round_trip(self):
        result = self._load_and_adapt("normalized_events.xlsx")
        assert len(result.normalized_data) == 2

    def test_xlsx_metadata_header(self):
        result = self._load_and_adapt("normalized_events_metadata_header.xlsx")
        assert result.provenance.header_row_index == 2
        assert len(result.normalized_data) == 2

    def test_decimal_comma_normalized(self):
        result = self._load_and_adapt("normalized_events_semicolon_decimalcomma.csv")
        assert len(result.normalized_data) == 2
        kvp_vals = result.normalized_data["kVp"].dropna()
        assert (kvp_vals > 0).all(), "decimal-comma kVp should parse as positive floats"
        assert any("decimal-comma" in w for w in result.warnings)

    def test_provenance_populated(self):
        result = self._load_and_adapt("normalized_events.csv")
        prov = result.provenance
        assert prov.schema_name == "normalized"
        assert prov.header_row_index == 0
        assert prov.original_filename == "normalized_events.csv"
        assert len(prov.column_map) == 23

    def test_missing_required_column_raises(self, tmp_path):
        from mypyskindose.input_adapters import normalized as adapter
        from mypyskindose.input_adapters.tabular_loader import read_csv

        # CSV missing kVp column
        csv_text = "model,DSD,DSI,DID,DSIRP,acquisition_type,acquisition_plane\nX,1,2,3,4,Fluoro,Single\n"
        p = tmp_path / "bad.csv"
        p.write_text(csv_text, encoding="utf-8")
        loaded = read_csv(p)
        with pytest.raises(ValueError, match="Missing required"):
            adapter.adapt(loaded, original_filename="bad.csv")

    def test_multistudy_splits(self):
        from mypyskindose.input_adapters import normalized as adapter
        from mypyskindose.input_adapters.tabular_loader import read_csv

        loaded = read_csv(FIXTURES / "normalized_events_multistudy.csv")
        results = adapter.adapt(loaded, original_filename="normalized_events_multistudy.csv")
        assert isinstance(results, list), "multi-study file should return a list"
        assert len(results) == 2, "fixture has two distinct study IDs"
        study_ids = {r.study_id for r in results}
        assert study_ids == {"A001", "A002"}
        for r in results:
            assert len(r.normalized_data) == 1
            assert r.provenance.schema_name == "normalized"

    def test_multistudy_single_study_returns_single(self):
        result = self._load_and_adapt("normalized_events.csv")
        assert not isinstance(result, list), "single-study file must return InputAdapterResult, not list"

    def test_kvp_values_are_numeric(self):
        result = self._load_and_adapt("normalized_events.csv")
        assert pd.api.types.is_numeric_dtype(result.normalized_data["kVp"])


# ── registry ──────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_csv_routes_to_normalized(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(FIXTURES / "normalized_events.csv")
        assert isinstance(result, InputAdapterResult)
        assert result.provenance.schema_name == "normalized"
        assert len(result.normalized_data) == 2

    def test_xlsx_routes_to_normalized(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(FIXTURES / "normalized_events.xlsx")
        assert isinstance(result, InputAdapterResult)
        assert len(result.normalized_data) == 2

    def test_multistudy_csv_returns_list(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(FIXTURES / "normalized_events_multistudy.csv")
        assert isinstance(result, list)
        assert len(result) == 2

    def test_unknown_schema_raises(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        with pytest.raises(ValueError, match="Unknown schema"):
            read_and_normalize_input(FIXTURES / "normalized_events.csv", input_schema="bogus")

    def test_dicom_suffix_raises(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        with pytest.raises(ValueError, match="Unsupported suffix"):
            read_and_normalize_input(Path("scan.dcm"))


# ── generic_rdsr_like adapter ─────────────────────────────────────────────────


def _default_settings():
    from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS
    from mypyskindose.settings import PyskindoseSettings

    return PyskindoseSettings(DEVELOPMENT_PARAMETERS)


GENERIC_RDSR_FIXTURE = FIXTURES / "generic_rdsr_events.csv"


class TestGenericRdsrAdapter:
    def test_csv_round_trip(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            GENERIC_RDSR_FIXTURE,
            input_schema="generic_rdsr_like",
            settings=_default_settings(),
        )
        assert result.provenance.schema_name == "generic_rdsr_like"
        assert len(result.normalized_data) == 21

    def test_normalized_columns_present(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            GENERIC_RDSR_FIXTURE,
            input_schema="generic_rdsr_like",
            settings=_default_settings(),
        )
        expected = {"model", "DSD", "DSI", "DID", "DSIRP", "kVp", "K_IRP", "Ap1", "Ap2"}
        assert expected.issubset(set(result.normalized_data.columns))

    def test_kvp_numeric(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            GENERIC_RDSR_FIXTURE,
            input_schema="generic_rdsr_like",
            settings=_default_settings(),
        )
        assert pd.api.types.is_numeric_dtype(result.normalized_data["kVp"])
        assert (result.normalized_data["kVp"] > 0).all()

    def test_provenance_populated(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            GENERIC_RDSR_FIXTURE,
            input_schema="generic_rdsr_like",
            settings=_default_settings(),
        )
        prov = result.provenance
        assert prov.schema_name == "generic_rdsr_like"
        assert prov.header_row_index == 0
        assert "KVP_kV" in prov.column_map.values()
        assert "DoseRP_Gy" in prov.column_map.values()

    def test_missing_settings_raises(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        with pytest.raises(ValueError, match="settings is required"):
            read_and_normalize_input(GENERIC_RDSR_FIXTURE, input_schema="generic_rdsr_like")

    def test_missing_required_column_raises(self, tmp_path):
        from mypyskindose.input_adapters import generic_rdsr as adapter
        from mypyskindose.input_adapters.tabular_loader import read_csv

        # CSV missing Manufacturer column
        csv_text = (
            "ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
            "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
            "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,"
            "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
            "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy\n"
            "AXIOM-Artis,Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,"
            "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003\n"
        )
        p = tmp_path / "bad.csv"
        p.write_text(csv_text, encoding="utf-8")
        loaded = read_csv(p)
        with pytest.raises(ValueError, match="Missing required"):
            adapter.adapt(loaded, original_filename="bad.csv", settings=_default_settings())


# ── schema auto-detection ─────────────────────────────────────────────────────


class TestSchemaAutoDetect:
    def test_auto_detects_normalized(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(FIXTURES / "normalized_events.csv", input_schema="auto")
        assert isinstance(result, InputAdapterResult)
        assert result.provenance.schema_name == "normalized"

    def test_auto_detects_generic_rdsr(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            GENERIC_RDSR_FIXTURE,
            input_schema="auto",
            settings=_default_settings(),
        )
        assert isinstance(result, InputAdapterResult)
        assert result.provenance.schema_name == "generic_rdsr_like"

    def test_auto_raises_on_no_match(self, tmp_path):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        p = tmp_path / "random.csv"
        p.write_text("col_a,col_b,col_c\n1,2,3\n4,5,6\n", encoding="utf-8")
        with pytest.raises(ValueError, match="auto-detection"):
            read_and_normalize_input(p, input_schema="auto")

    def test_auto_failure_is_schema_detection_error(self, tmp_path):
        """Auto-detection failures raise the specific SchemaDetectionError subclass
        (still a ValueError) so callers like the GUI can show a "choose a schema"
        hint instead of treating it as a parse error."""
        from mypyskindose.input_adapters.registry import (
            SchemaDetectionError,
            read_and_normalize_input,
        )

        p = tmp_path / "random.csv"
        p.write_text("col_a,col_b,col_c\n1,2,3\n4,5,6\n", encoding="utf-8")
        with pytest.raises(SchemaDetectionError):
            read_and_normalize_input(p, input_schema="auto")

    def test_auto_detect_is_scale_independent_for_wide_exports(self):
        """A wide export (all of a schema's known names plus many unrelated
        columns) must auto-detect that schema, not read as 'ambiguous'.

        Real Radimetrics CSVs carry ~87 columns of which 13 are recognised — a
        low precision (13/87) but a full recall (13/13). Scoring on recall keeps
        detection scale-independent; the earlier precision score made such wide
        files tie with any schema that matched a single stray column.
        """
        import pandas as pd

        from mypyskindose.input_adapters.generic_rdsr import GENERIC_RDSR_COLUMN_NAMES
        from mypyskindose.input_adapters.radimetrics import RADIMETRICS_COLUMN_NAMES
        from mypyskindose.input_adapters.registry import _detect_schema
        from mypyskindose.input_adapters.tabular_loader import _RawLoad

        # Header = every radimetrics known name (full recall) + a single stray
        # generic_rdsr column + many unrelated filler columns (drives precision down).
        stray_generic = sorted(GENERIC_RDSR_COLUMN_NAMES)[0]
        header = (
            sorted(RADIMETRICS_COLUMN_NAMES)
            + [stray_generic]
            + [f"Unrelated Column {i}" for i in range(70)]
        )
        data_row = ["x"] * len(header)
        raw_df = pd.DataFrame([header, data_row])

        assert _detect_schema(_RawLoad(raw_df=raw_df, encoding="utf-8", delimiter=",")) == "radimetrics"


# ── radimetrics adapter ────────────────────────────────────────────────────────

RADIMETRICS_FIXTURE = FIXTURES / "radimetrics_events.csv"
DOSETRACK_FIXTURE = FIXTURES / "dosetrack_events.csv"


class TestRadimetricsAdapter:
    def test_csv_round_trip(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_FIXTURE,
            input_schema="radimetrics",
            settings=_default_settings(),
        )
        assert result.provenance.schema_name == "radimetrics"
        assert len(result.normalized_data) == 5

    def test_normalized_columns_present(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_FIXTURE,
            input_schema="radimetrics",
            settings=_default_settings(),
        )
        expected = {"model", "DSD", "DSI", "DID", "kVp", "K_IRP", "Ap1", "Ap2"}
        assert expected.issubset(set(result.normalized_data.columns))

    def test_unit_conversions_applied(self):
        """DoseRP should be in Gy after /1000 conversion from mGy."""
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_FIXTURE,
            input_schema="radimetrics",
            settings=_default_settings(),
        )
        # Source: 0.030 mGy → 3e-05 Gy in K_IRP
        assert result.provenance.unit_conversions.get("DoseRP_Gy") == "mGy → Gy"
        assert result.provenance.unit_conversions.get("CollimatedFieldArea_m2") == "cm² → m²"

    def test_kvp_numeric_and_positive(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_FIXTURE,
            input_schema="radimetrics",
            settings=_default_settings(),
        )
        assert pd.api.types.is_numeric_dtype(result.normalized_data["kVp"])
        assert (result.normalized_data["kVp"] > 0).all()

    def test_provenance_populated(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_FIXTURE,
            input_schema="radimetrics",
            settings=_default_settings(),
        )
        prov = result.provenance
        assert prov.schema_name == "radimetrics"
        assert prov.header_row_index == 0
        assert "KVP_kV" in prov.column_map.values()
        assert "DoseRP_Gy" in prov.column_map.values()

    def test_missing_settings_raises(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        with pytest.raises(ValueError, match="settings is required"):
            read_and_normalize_input(RADIMETRICS_FIXTURE, input_schema="radimetrics")

    def test_missing_required_column_raises(self, tmp_path):
        from mypyskindose.input_adapters import radimetrics as adapter
        from mypyskindose.input_adapters.tabular_loader import read_csv

        # CSV missing kVp kV column
        csv_text = (
            "Manufacturer,Device,Source To Detector Distance (RF) [mm],"
            "Source To Isocenter Distance (RF) [mm],"
            "Table Longitudinal Position [mm],Table Lateral Position [mm],"
            "Table Height Position [mm],Primary Angle (RF) [°],Secondary Angle (RF) [°],"
            "Reference Point Dose (Total) mGy\n"
            "Siemens,AXIOM-Artis,1198.0,785.0,37.8,40.6,294.1,-0.1,-1.1,0.030\n"
        )
        p = tmp_path / "bad.csv"
        p.write_text(csv_text, encoding="utf-8")
        loaded = read_csv(p)
        with pytest.raises(ValueError, match="Missing required"):
            adapter.adapt(loaded, original_filename="bad.csv", settings=_default_settings())

    def test_auto_detects_radimetrics(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_FIXTURE,
            input_schema="auto",
            settings=_default_settings(),
        )
        assert isinstance(result, InputAdapterResult)
        assert result.provenance.schema_name == "radimetrics"


# An older Radimetrics export uses underscored headers, no unit suffixes, a
# numeric first row above the header, and a bare "Reference_Point_Dose" total
# alongside per-plane "_(A/B)_mGy" columns. Matching normalizes separators so the
# underscored headers map, and the bare-total pattern is disambiguated from the
# per-plane columns by coverage.
RADIMETRICS_LEGACY_FIXTURE = FIXTURES / "radimetrics_events_legacy.csv"


class TestRadimetricsLegacyFormat:
    def test_auto_detects_and_loads(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_LEGACY_FIXTURE,
            input_schema="auto",
            settings=_default_settings(),
        )
        assert isinstance(result, InputAdapterResult)
        assert result.provenance.schema_name == "radimetrics"
        assert len(result.normalized_data) == 3
        # header is the 2nd row (row 0 is a numeric index row)
        assert result.provenance.header_row_index == 1
        expected = {"model", "DSD", "DSI", "kVp", "K_IRP", "Ap1", "Ap2"}
        assert expected.issubset(set(result.normalized_data.columns))

    def test_total_reference_dose_mapped_not_per_plane(self):
        """The bare total column maps to DoseRP_Gy; the per-plane (A)/(B) columns
        do not. K_IRP follows the total (30/20/50), not (A) 18/12/30."""
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            RADIMETRICS_LEGACY_FIXTURE,
            input_schema="auto",
            settings=_default_settings(),
        )
        assert isinstance(result, InputAdapterResult)
        col_map = result.provenance.column_map
        dose_sources = [src for src, tgt in col_map.items() if tgt == "DoseRP_Gy"]
        assert dose_sources == ["Reference_Point_Dose"]
        assert result.normalized_data["K_IRP"].tolist() == [30.0, 20.0, 50.0]


class TestDoseTrackAdapter:
    def test_csv_round_trip(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        assert result.provenance.schema_name == "dosetrack"
        assert len(result.normalized_data) == 5

    def test_normalized_columns_present(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        expected = {"model", "DSD", "DSI", "DID", "kVp", "K_IRP", "Ap1", "Ap2"}
        assert expected.issubset(set(result.normalized_data.columns))

    def test_unit_conversions_applied(self):
        """Air Kerma should be converted mGy→Gy; DAP Gy·cm²→Gy·m²."""
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        assert result.provenance.unit_conversions.get("DoseRP_Gy") == "mGy → Gy"
        assert "DoseAreaProduct_Gym2" in result.provenance.unit_conversions

    def test_manufacturer_inferred_from_equipment_name(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        assert (result.normalized_data["model"] == "AXIOM-Artis").all()

    def test_plane_code_normalized(self):
        """Integer Plane Code 1 → 'Single Plane' before rdsr_normalizer."""
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        # rdsr_normalizer maps acquisition_plane; we just need a successful result
        assert len(result.normalized_data) == 5

    def test_kvp_numeric_and_positive(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        assert pd.api.types.is_numeric_dtype(result.normalized_data["kVp"])
        assert (result.normalized_data["kVp"] > 0).all()

    def test_provenance_populated(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="dosetrack",
            settings=_default_settings(),
        )
        prov = result.provenance
        assert prov.schema_name == "dosetrack"
        assert prov.header_row_index == 0
        assert "KVP_kV" in prov.column_map.values()
        assert "DoseRP_Gy" in prov.column_map.values()

    def test_missing_settings_raises(self):
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        with pytest.raises(ValueError, match="settings is required"):
            read_and_normalize_input(DOSETRACK_FIXTURE, input_schema="dosetrack")

    def test_missing_equipment_name_raises(self, tmp_path):
        from mypyskindose.input_adapters import dosetrack as adapter
        from mypyskindose.input_adapters.tabular_loader import read_csv

        # CSV without Equipment Name → cannot infer manufacturer
        csv_text = (
            "Plane Code,Air Kerma (mGy),Tube Voltage Peak (kV),"
            "Distance Source to Detector (mm),Distance Source To Isocenter (mm),"
            "Table Longitudinal Position (mm),Table Lateral Position (mm),"
            "Table Height Position (mm),Positioner Primary Angle (deg),"
            "Positioner Secondary Angle (deg),Filter Thickness,DAP (Gy*cm2)\n"
            "1,15.0,70,1000,750,0,0,290,0,0,0.1,0.54\n"
        )
        p = tmp_path / "no_equip.csv"
        p.write_text(csv_text, encoding="utf-8")
        loaded = read_csv(p)
        with pytest.raises(ValueError, match="Equipment Name"):
            adapter.adapt(loaded, original_filename="no_equip.csv", settings=_default_settings())

    def test_auto_detects_dosetrack(self):
        from mypyskindose.input_adapters.models import InputAdapterResult
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            DOSETRACK_FIXTURE,
            input_schema="auto",
            settings=_default_settings(),
        )
        assert isinstance(result, InputAdapterResult)
        assert result.provenance.schema_name == "dosetrack"
