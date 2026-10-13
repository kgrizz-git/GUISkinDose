"""Tests for the Phase 1 per-exam equipment identity contract.

Covers the `exam_identity` seam (cleaning, raw pair listing, canonical pairs,
classification, fail-closed guard), the canonical `manufacturer` column on every
raw-normalized frame path (DICOM via parser, raw-shaped tabular via the
normalizer, DoseTrack per-row mapping), the recognized optional `manufacturer`
column on the `normalized` schema with its legacy count-only warning, and the
pair-consistent export identity lookup. This is identity only: no custom
coordinates are applied, no store is read, and numeric results are unchanged
(pinned by the golden suites).

Contract rule: one exam carries exactly one canonical (manufacturer, model)
pair — both axes through the existing key normalizers, no vendor aliases.
Same-maker model variation, distinct canonical makers, and known+unknown mixes
are all rejected; only key spelling variants collapse and only an all-unknown
frame stays compatible (legacy model-only path).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from guiskindose.exam_identity import (
    HOMOGENEOUS,
    MISSING_MANUFACTURER,
    MIXED_MANUFACTURER,
    MODEL_VARIATION,
    canonical_identity_pairs,
    classify_exam_identity,
    clean_identity_value,
    frame_identities,
    missing_maker_rows,
    require_homogeneous_identity,
)
from guiskindose.rdsr_input_checks import RdsrInputError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabular_inputs"

_RAW_HEADER = (
    "Manufacturer,ManufacturerModelName,IrradiationEventType,AcquisitionPlane,"
    "DistanceSourcetoDetector_mm,DistanceSourcetoIsocenter_mm,"
    "TableLongitudinalPosition_mm,TableLateralPosition_mm,TableHeightPosition_mm,CollimatedFieldArea_m2,"
    "XRayFilterMaterial,XRayFilterThicknessMinimum_mm,XRayFilterThicknessMaximum_mm,"
    "PositionerPrimaryAngle_deg,PositionerSecondaryAngle_deg,KVP_kV,DoseRP_Gy"
)
_RAW_ROW = (
    "{maker},{model},Fluoroscopy,Single Plane,1198,785,37.8,40.6,294.1,0.01,"
    "Copper or Copper compound,0.6,0.6,-0.1,-1.1,77.0,0.00003"
)

_NORMALIZED_REQUIRED = (
    "model,DSD,DSI,DID,DSIRP,acquisition_type,acquisition_plane,"
    "Tx,Ty,Tz,At1,At2,At3,filter_thickness_Cu,filter_thickness_Al,"
    "Ap1,Ap2,Ap3,DSL,FS_lat,FS_long,kVp,K_IRP"
)
_NORMALIZED_ROW = (
    "X,1,2,3,4,Fluoroscopy,Single Plane,0,0,0,0,0,0,0,0,0,0,0,20,10,10,80,0.01"
)

_DOSETRACK_HEADER = (
    "Equipment Name,Plane Code,Air Kerma (mGy),Tube Voltage Peak (kV),"
    "Distance Source to Detector (mm),Distance Source To Isocenter (mm),"
    "Table Longitudinal Position (mm),Table Lateral Position (mm),"
    "Table Height Position (mm),Positioner Primary Angle (deg),"
    "Positioner Secondary Angle (deg),Filter Thickness,DAP (Gy*cm2)"
)
_DOSETRACK_ROW = (
    "{equip},113622,15.0,70,1000,750,0,0,290,0,0,0.1,0.54"
)


def _default_settings():
    from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS

    from guiskindose.settings import PyskindoseSettings

    return PyskindoseSettings(DEVELOPMENT_PARAMETERS)


def _raw_csv(maker: str, model: str = "AXIOM-Artis") -> str:
    return _RAW_HEADER + "\n" + _RAW_ROW.format(maker=maker, model=model) + "\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _adapt_raw(text: str, tmp_path: Path, name: str = "events.csv"):
    from guiskindose.input_adapters import generic_rdsr as adapter
    from guiskindose.input_adapters.tabular_loader import read_csv

    loaded = read_csv(_write(tmp_path, name, text))
    return adapter.adapt(loaded, original_filename=name, settings=_default_settings())


def _adapt_normalized(text: str, tmp_path: Path, name: str = "events.csv"):
    from guiskindose.input_adapters import normalized as adapter
    from guiskindose.input_adapters.tabular_loader import read_csv

    loaded = read_csv(_write(tmp_path, name, text))
    return adapter.adapt(loaded, original_filename=name)


def _adapt_dosetrack(text: str, tmp_path: Path, name: str = "events.csv"):
    from guiskindose.input_adapters import dosetrack as adapter
    from guiskindose.input_adapters.tabular_loader import read_csv

    loaded = read_csv(_write(tmp_path, name, text))
    return adapter.adapt(loaded, original_filename=name, settings=_default_settings())


# ── cleaning ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [None, float("nan"), "", "   ", "nan", "NaN", " NAN ", "nat", "NAT", "none", "None", "NONE"],
)
def test_clean_identity_value_maps_missing_to_none(raw: object) -> None:
    assert clean_identity_value(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Siemens", "Siemens"), ("  SIEMENS  ", "SIEMENS"), ("Philips Medical", "Philips Medical"), ("0", "0")],
)
def test_clean_identity_value_preserves_exact_spelling(raw: object, expected: str) -> None:
    assert clean_identity_value(raw) == expected


# ── pair listing (raw + canonical) ────────────────────────────────────────


def test_frame_identities_first_appearance_order() -> None:
    frame = pd.DataFrame(
        {
            "manufacturer": ["Siemens", "Siemens", "Philips", None],
            "model": ["A", "A", "B", "C"],
        }
    )
    assert frame_identities(frame) == (
        ("Siemens", "A"),
        ("Philips", "B"),
        (None, "C"),
    )


def test_frame_identities_empty_frame() -> None:
    assert frame_identities(pd.DataFrame()) == ()


def test_canonical_pairs_collapse_key_variants() -> None:
    frame = pd.DataFrame(
        {"manufacturer": ["SIEMENS", "Siemens ", "Siemens."], "model": ["AXIOM-Artis", "AXIOM Artis", "axiom_artis"]}
    )
    assert canonical_identity_pairs(frame) == (("siemens", "axiom artis"),)


def test_canonical_pairs_keep_distinct_keys_distinct() -> None:
    frame = pd.DataFrame(
        {"manufacturer": ["Siemens", "Siemens Healthcare"], "model": ["A", "A"]}
    )
    assert canonical_identity_pairs(frame) == (("siemens", "a"), ("siemens healthcare", "a"))


def test_canonical_pairs_map_blanks_to_none() -> None:
    frame = pd.DataFrame({"manufacturer": [None, ""], "model": ["A", "  "]})
    assert canonical_identity_pairs(frame) == ((None, "a"), (None, None))


def test_missing_maker_rows_counts_blanks() -> None:
    frame = pd.DataFrame({"manufacturer": ["Siemens", None, "", "nan"], "model": ["A", "A", "A", "A"]})
    assert missing_maker_rows(frame) == 3
    assert missing_maker_rows(pd.DataFrame({"model": ["A"]})) == 1


# ── classification (descriptive) ──────────────────────────────────────────


def test_classify_homogeneous() -> None:
    frame = pd.DataFrame({"manufacturer": ["Siemens", "SIEMENS"], "model": ["A", "A"]})
    assert classify_exam_identity(frame) == HOMOGENEOUS


def test_classify_missing_manufacturer() -> None:
    frame = pd.DataFrame({"manufacturer": [None, None], "model": ["A", "A"]})
    assert classify_exam_identity(frame) == MISSING_MANUFACTURER


def test_classify_model_variation_same_maker() -> None:
    frame = pd.DataFrame({"manufacturer": ["Siemens", "Siemens"], "model": ["A", "B"]})
    assert classify_exam_identity(frame) == MODEL_VARIATION


def test_classify_mixed_manufacturers() -> None:
    frame = pd.DataFrame({"manufacturer": ["Siemens", "Philips"], "model": ["A", "B"]})
    assert classify_exam_identity(frame) == MIXED_MANUFACTURER


def test_classify_distinct_canonical_keys_are_mixed() -> None:
    """Different canonical keys are different identities — even alias-family spellings.

    ``"Siemens Healthcare"`` key-normalizes to ``"siemens healthcare"``, not
    ``"siemens"``. Bundled alias matching may unite them later (Phase 2+), but
    identity classification compares canonical keys, so the frame is mixed.
    """
    frame = pd.DataFrame(
        {"manufacturer": ["Siemens", "Siemens Healthcare"], "model": ["A", "A"]}
    )
    assert classify_exam_identity(frame) == MIXED_MANUFACTURER


# ── fail-closed guard ─────────────────────────────────────────────────────


def test_require_homogeneous_identity_rejects_mixed_value_free() -> None:
    frame = pd.DataFrame({"manufacturer": ["Siemens", "Philips"], "model": ["A", "B"]})
    with pytest.raises(RdsrInputError) as excinfo:
        require_homogeneous_identity(frame)
    message = str(excinfo.value)
    assert "2 distinct equipment identities" in message
    assert "Siemens" not in message
    assert "Philips" not in message


def test_require_homogeneous_identity_rejects_same_maker_model_variation() -> None:
    """One maker with two models is two identities: no row borrows row 0's model."""
    frame = pd.DataFrame({"manufacturer": ["Siemens", "Siemens"], "model": ["A", "B"]})
    with pytest.raises(RdsrInputError, match="2 distinct equipment identities"):
        require_homogeneous_identity(frame)


def test_require_homogeneous_identity_rejects_known_plus_unknown() -> None:
    """Known rows beside unknown rows fail, counting the rows without identity."""
    frame = pd.DataFrame({"manufacturer": ["Siemens", None, ""], "model": ["A", "A", "A"]})
    with pytest.raises(RdsrInputError) as excinfo:
        require_homogeneous_identity(frame)
    message = str(excinfo.value)
    assert "2 distinct equipment identities" in message
    assert "2 event(s) without maker identity" in message


def test_require_homogeneous_identity_uses_opaque_position_only() -> None:
    frame = pd.DataFrame({"manufacturer": ["Siemens", "Philips"], "model": ["A", "B"]})
    with pytest.raises(RdsrInputError) as excinfo:
        require_homogeneous_identity(frame, exam_index=2)
    assert str(excinfo.value).startswith("Exam 3:")
    with pytest.raises(ValueError, match="exam index"):
        require_homogeneous_identity(frame, exam_index=-1)


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"manufacturer": ["Siemens", "SIEMENS"], "model": ["A", "A"]}),
        pd.DataFrame({"manufacturer": ["Siemens.", " siemens "], "model": ["AXIOM-Artis", "AXIOM Artis"]}),
        pd.DataFrame({"manufacturer": [None, None], "model": ["A", "A"]}),
        pd.DataFrame({"manufacturer": [None, None], "model": [None, None]}),
    ],
)
def test_require_homogeneous_identity_passes_uniform_frames(frame: pd.DataFrame) -> None:
    require_homogeneous_identity(frame)


# ── raw-normalized frame paths ────────────────────────────────────────────


def test_raw_tabular_emits_exact_manufacturer_column(tmp_path: Path) -> None:
    result = _adapt_raw(_raw_csv("Siemens Healthcare"), tmp_path)
    frame = result.normalized_data
    assert list(frame["manufacturer"]) == ["Siemens Healthcare"]
    assert list(frame["model"]) == ["AXIOM-Artis"]


def test_raw_tabular_mixed_manufacturers_fail_closed(tmp_path: Path) -> None:
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(maker="Siemens", model="A") + "\n" + _RAW_ROW.format(
        maker="Philips", model="B"
    ) + "\n"
    with pytest.raises(RdsrInputError) as excinfo:
        _adapt_raw(text, tmp_path)
    message = str(excinfo.value)
    assert "Siemens" not in message
    assert "Philips" not in message


def test_raw_tabular_same_maker_different_models_fail_closed(tmp_path: Path) -> None:
    """Same maker, two models: the second model must not silently take the first's coordinates."""
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(maker="Siemens", model="A") + "\n" + _RAW_ROW.format(
        maker="Siemens", model="B"
    ) + "\n"
    with pytest.raises(RdsrInputError, match="2 distinct equipment identities"):
        _adapt_raw(text, tmp_path)


def test_raw_tabular_known_plus_blank_maker_fails_with_missing_count(tmp_path: Path) -> None:
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(maker="Siemens", model="A") + "\n" + _RAW_ROW.format(
        maker="", model="A"
    ) + "\n"
    with pytest.raises(RdsrInputError) as excinfo:
        _adapt_raw(text, tmp_path)
    assert "1 event(s) without maker identity" in str(excinfo.value)


def test_raw_tabular_key_variants_are_one_identity(tmp_path: Path) -> None:
    text = _RAW_HEADER + "\n" + _RAW_ROW.format(maker="SIEMENS", model="AXIOM-Artis") + "\n" + _RAW_ROW.format(
        maker="Siemens.", model="AXIOM Artis"
    ) + "\n"
    result = _adapt_raw(text, tmp_path)
    assert len(result.normalized_data) == 2


def test_dicom_path_emits_manufacturer_column() -> None:
    pydicom = pytest.importorskip("pydicom")
    from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
    from guiskindose.rdsr_normalizer import rdsr_normalizer
    from guiskindose.rdsr_parser import rdsr_parser
    from guiskindose.settings import PyskindoseSettings

    raw = pydicom.dcmread(str(get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"))
    parsed = rdsr_parser(raw, silence_pydicom_warnings=True)
    settings = PyskindoseSettings(settings=load_settings_example_json())
    normalized = rdsr_normalizer(parsed, settings)
    assert list(normalized["manufacturer"].unique()) == ["Siemens"]
    assert list(normalized["model"].unique()) == ["AXIOM-Artis"]


# ── DoseTrack per-row identity ────────────────────────────────────────────


def _dosetrack_csv(equipment: list[str]) -> str:
    return _DOSETRACK_HEADER + "\n" + "\n".join(_DOSETRACK_ROW.format(equip=name) for name in equipment) + "\n"


def test_dosetrack_homogeneous_maps_per_row(tmp_path: Path) -> None:
    result = _adapt_dosetrack(_dosetrack_csv(["AXIOM-Artis", "AXIOM-Artis"]), tmp_path)
    frame = result.normalized_data
    assert list(frame["manufacturer"]) == ["Siemens", "Siemens"]
    assert list(frame["model"]) == ["AXIOM-Artis", "AXIOM-Artis"]


def test_dosetrack_mixed_equipment_fails_before_overwrite(tmp_path: Path) -> None:
    """Two makers from Equipment Name fail closed; no whole-column first-name overwrite."""
    csv_text = _dosetrack_csv(["AXIOM-Artis", "Azurion"])
    with pytest.raises(RdsrInputError) as excinfo:
        _adapt_dosetrack(csv_text, tmp_path)
    message = str(excinfo.value)
    assert "AXIOM-Artis" not in message
    assert "Azurion" not in message


def test_dosetrack_same_maker_different_equipment_fails(tmp_path: Path) -> None:
    """Two Philips equipment names are two models: rejected, not merged under the first."""
    csv_text = _dosetrack_csv(["Azurion", "Allura Clarity"])
    with pytest.raises(RdsrInputError, match="2 distinct equipment identities"):
        _adapt_dosetrack(csv_text, tmp_path)


def test_dosetrack_unknown_name_warns_count_only(tmp_path: Path) -> None:
    result = _adapt_dosetrack(_dosetrack_csv(["MysteryScope 9"]), tmp_path)
    assert list(result.normalized_data["manufacturer"]) == ["MysteryScope 9"]
    assert list(result.normalized_data["model"]) == ["MysteryScope 9"]
    unknown = [warning for warning in result.warnings if "outside the known list" in warning]
    assert len(unknown) == 1
    assert "1 event(s)" in unknown[0]
    assert "MysteryScope 9" not in unknown[0]


def test_dosetrack_blank_continuation_fills_hierarchical(tmp_path: Path) -> None:
    """Blank Equipment Name cells repeat the previous row (hierarchical exports)."""
    result = _adapt_dosetrack(_dosetrack_csv(["AXIOM-Artis", ""]), tmp_path)
    assert list(result.normalized_data["manufacturer"]) == ["Siemens", "Siemens"]
    assert list(result.normalized_data["model"]) == ["AXIOM-Artis", "AXIOM-Artis"]


def test_dosetrack_leading_blank_plus_known_fails_with_missing_count(tmp_path: Path) -> None:
    """A leading blank cannot borrow the later row's identity."""
    csv_text = _dosetrack_csv(["", "AXIOM-Artis"])
    with pytest.raises(RdsrInputError) as excinfo:
        _adapt_dosetrack(csv_text, tmp_path)
    assert "1 event(s) without maker identity" in str(excinfo.value)


# ── normalized schema: explicit manufacturer ──────────────────────────────


def _normalized_csv(*, manufacturer_header: str | None, makers: list[str]) -> str:
    header = _NORMALIZED_REQUIRED + (f",{manufacturer_header}" if manufacturer_header else "")
    if len(makers) == 1:
        rows = [_NORMALIZED_ROW + (f",{makers[0]}" if manufacturer_header else "")]
    else:
        rows = [
            _NORMALIZED_ROW + (f",{maker}" if manufacturer_header else "") for maker in makers
        ]
    return header + "\n" + "\n".join(rows) + "\n"


def test_normalized_explicit_manufacturer_preserved(tmp_path: Path) -> None:
    result = _adapt_normalized(
        _normalized_csv(manufacturer_header="manufacturer", makers=["Siemens Healthcare"]), tmp_path
    )
    assert not isinstance(result, list)
    assert list(result.normalized_data["manufacturer"]) == ["Siemens Healthcare"]
    assert list(result.normalized_data["model"]) == ["X"]
    assert not any("manufacturer column absent" in warning for warning in result.warnings)


def test_normalized_manufacturer_header_case_insensitive(tmp_path: Path) -> None:
    result = _adapt_normalized(
        _normalized_csv(manufacturer_header="Manufacturer", makers=["Philips"]), tmp_path
    )
    assert not isinstance(result, list)
    assert list(result.normalized_data["manufacturer"]) == ["Philips"]


def test_normalized_blank_manufacturer_values_become_none(tmp_path: Path) -> None:
    result = _adapt_normalized(_normalized_csv(manufacturer_header="manufacturer", makers=[""]), tmp_path)
    assert not isinstance(result, list)
    assert result.normalized_data["manufacturer"].tolist() == [None]
    assert any("no identity" in warning for warning in result.warnings)


def test_normalized_legacy_missing_column_warns_count_only(tmp_path: Path) -> None:
    result = _adapt_normalized(_normalized_csv(manufacturer_header=None, makers=["X"]), tmp_path)
    assert not isinstance(result, list)
    assert result.normalized_data["manufacturer"].tolist() == [None]
    legacy = [warning for warning in result.warnings if "manufacturer column absent" in warning]
    assert len(legacy) == 1
    assert "1 event(s)" in legacy[0]


def test_normalized_legacy_fixture_warns_count_only() -> None:
    from guiskindose.input_adapters import normalized as adapter
    from guiskindose.input_adapters.tabular_loader import read_csv

    result = adapter.adapt(read_csv(FIXTURES / "normalized_events.csv"), original_filename="x.csv")
    assert not isinstance(result, list)
    assert result.normalized_data["manufacturer"].tolist() == [None, None]
    legacy = [warning for warning in result.warnings if "manufacturer column absent" in warning]
    assert len(legacy) == 1
    assert "2 event(s)" in legacy[0]


def test_normalized_mixed_manufacturers_fail_closed_value_free(tmp_path: Path) -> None:
    header = _NORMALIZED_REQUIRED + ",manufacturer"
    text = header + "\n" + _NORMALIZED_ROW + ",Siemens\n" + _NORMALIZED_ROW + ",Philips\n"
    with pytest.raises(ValueError, match="2 distinct equipment identities") as excinfo:
        _adapt_normalized(text, tmp_path)
    assert "Siemens" not in str(excinfo.value)
    assert "Philips" not in str(excinfo.value)


def test_normalized_same_maker_different_models_fail_closed(tmp_path: Path) -> None:
    header = _NORMALIZED_REQUIRED + ",manufacturer"
    text = (
        header
        + "\n"
        + _NORMALIZED_ROW.replace("X,1,2", "A,1,2", 1)
        + ",Siemens\n"
        + _NORMALIZED_ROW.replace("X,1,2", "B,1,2", 1)
        + ",Siemens\n"
    )
    with pytest.raises(ValueError, match="2 distinct equipment identities"):
        _adapt_normalized(text, tmp_path)


def test_normalized_key_variants_are_one_identity(tmp_path: Path) -> None:
    header = _NORMALIZED_REQUIRED + ",manufacturer"
    text = header + "\n" + _NORMALIZED_ROW + ",SIEMENS\n" + _NORMALIZED_ROW + ",Siemens.\n"
    result = _adapt_normalized(text, tmp_path)
    assert not isinstance(result, list)
    assert len(result.normalized_data) == 2


def test_normalized_known_plus_blank_maker_fails_with_missing_count(tmp_path: Path) -> None:
    header = _NORMALIZED_REQUIRED + ",manufacturer"
    text = header + "\n" + _NORMALIZED_ROW + ",Siemens\n" + _NORMALIZED_ROW + ",\n"
    with pytest.raises(ValueError) as excinfo:
        _adapt_normalized(text, tmp_path)
    message = str(excinfo.value)
    assert "2 distinct equipment identities" in message
    assert "1 event(s) without maker identity" in message
    assert "Siemens" not in message


def test_normalized_multi_study_makers_may_differ_across_groups(tmp_path: Path) -> None:
    header = _NORMALIZED_REQUIRED + ",manufacturer,StudyInstanceUID"
    text = (
        header
        + "\n"
        + _NORMALIZED_ROW
        + ",Siemens,UID-A\n"
        + _NORMALIZED_ROW
        + ",Philips,UID-B\n"
    )
    result = _adapt_normalized(text, tmp_path)
    assert isinstance(result, list)
    assert len(result) == 2
    makers = sorted(group.normalized_data["manufacturer"].iloc[0] for group in result)
    assert makers == ["Philips", "Siemens"]


def test_normalized_multi_study_distinct_models_accepted_without_loss(tmp_path: Path) -> None:
    """Same maker, different models across study groups: split keeps every event."""
    header = _NORMALIZED_REQUIRED + ",manufacturer,StudyInstanceUID"
    row_a = _NORMALIZED_ROW.replace("X,1,2", "A,1,2", 1)
    row_b = _NORMALIZED_ROW.replace("X,1,2", "B,1,2", 1)
    text = header + "\n" + row_a + ",Siemens,UID-A\n" + row_b + ",Siemens,UID-B\n"
    result = _adapt_normalized(text, tmp_path)
    assert isinstance(result, list)
    assert len(result) == 2
    assert [len(group.normalized_data) for group in result] == [1, 1]
    assert [group.normalized_data["model"].iloc[0] for group in result] == ["A", "B"]


def test_normalized_multi_study_mixed_within_one_group_fails(tmp_path: Path) -> None:
    header = _NORMALIZED_REQUIRED + ",manufacturer,StudyInstanceUID"
    text = (
        header
        + "\n"
        + _NORMALIZED_ROW
        + ",Siemens,UID-A\n"
        + _NORMALIZED_ROW
        + ",Philips,UID-A\n"
    )
    with pytest.raises(ValueError, match="distinct equipment identities") as excinfo:
        _adapt_normalized(text, tmp_path)
    message = str(excinfo.value)
    assert "UID-A" not in message
    assert "Siemens" not in message


# ── export identity lookup ────────────────────────────────────────────────


def test_first_present_skips_missing_value_artifacts() -> None:
    from guiskindose.export.sections import _first_present

    frame = pd.DataFrame({"manufacturer": [None, "nan", "None", "  ", "Siemens"]})
    assert _first_present(frame, "manufacturer") == "Siemens"
    assert _first_present(pd.DataFrame({"manufacturer": [None, "nan"]}), "manufacturer") is None
    assert _first_present(pd.DataFrame({"model": ["X"]}), "manufacturer") is None
    assert _first_present(None, "manufacturer") is None


def _exam_source(frame: pd.DataFrame):
    from guiskindose import load_settings_example_json
    from guiskindose.export.models import ExportExamSource
    from guiskindose.settings import PyskindoseSettings

    settings = PyskindoseSettings(settings=load_settings_example_json(), output_format="dict")
    return ExportExamSource("exam-1", frame, None, "events.csv", settings, (0, 0, 0))


def test_equipment_section_reports_new_column() -> None:
    from guiskindose.export.sections import equipment_section

    frame = pd.DataFrame({"manufacturer": ["Siemens", "Siemens"], "model": ["AXIOM-Artis", "AXIOM-Artis"]})
    section = equipment_section(_exam_source(frame))
    assert section["manufacturer"] == "Siemens"
    assert section["model"] == "AXIOM-Artis"


def test_equipment_section_legacy_frame_reports_no_maker() -> None:
    from guiskindose.export.sections import equipment_section

    frame = pd.DataFrame({"manufacturer": [None, None], "model": ["X", "X"]})
    section = equipment_section(_exam_source(frame))
    assert section["manufacturer"] is None
    assert section["model"] == "X"


def test_equipment_section_keeps_pair_consistent_across_rows() -> None:
    """Maker from one row is never paired with another row's model."""
    from guiskindose.export.sections import equipment_section

    frame = pd.DataFrame({"manufacturer": [None, "Philips"], "model": ["ModelA", "ModelB"]})
    section = equipment_section(_exam_source(frame))
    assert section["manufacturer"] == "Philips"
    assert section["model"] == "ModelB"


def test_equipment_section_missing_model_not_borrowed() -> None:
    """A maker-identified row with a blank model reports no model — not the next row's."""
    from guiskindose.export.sections import equipment_section

    frame = pd.DataFrame({"manufacturer": ["Siemens", "Philips"], "model": ["", "ModelB"]})
    section = equipment_section(_exam_source(frame))
    assert section["manufacturer"] == "Siemens"
    assert section["model"] is None
