"""Unit tests for the CSV and TSV equipment-profile adapters.

Covers the tabular slice only: strict headers and row widths, record-type applicability, grouping and ordering
independence, alias cell forms, canonical equivalence with the packaged JSON, hash and source-hash rules,
bounded reads, and value-free privacy behaviour. Factor, evidence, and grid policies are already agreed and are
not re-tested here; the adapter stays inert (no application wiring).
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from guiskindose.equipment_profiles import (
    FLAT_COLUMNS,
    MAX_SOURCE_BYTES,
    EquipmentProfileError,
    ProfileErrorCode,
    active_set_hash,
    canonical_profile_dict,
    combine_documents,
    parse_csv_bytes,
    parse_csv_file,
    parse_json_bytes,
    parse_tsv_bytes,
    parse_tsv_file,
    profile_hash,
    source_bytes_hash,
)

_EXAMPLE_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "equipment_profiles"
)
_CSV_PATH = _EXAMPLE_DIR / "equipment_profile_example.csv"
_JSON_PATH = _EXAMPLE_DIR / "equipment_profile_example.json"

_PROMOTION_COLUMN = "promote_coordinate_wildcard"
_FLAT_COLUMN_NAMES: tuple[str, ...] = tuple(FLAT_COLUMNS)
_WIDTH = len(_FLAT_COLUMN_NAMES)


def _code(excinfo: pytest.ExceptionInfo[EquipmentProfileError]) -> ProfileErrorCode:
    return excinfo.value.code


def _write(rows: list[list[str]], header: list[str] | None = None) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header if header is not None else list(_FLAT_COLUMN_NAMES))
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _blank(record_type: str, profile_id: str = "demo-partial", **overrides: str) -> list[str]:
    row = [""] * _WIDTH
    row[0] = record_type
    row[1] = profile_id
    for name, value in overrides.items():
        row[_FLAT_COLUMN_NAMES.index(name)] = value
    return row


def _profile_row(**overrides: str) -> list[str]:
    base = {
        "record_type": "profile",
        "profile_id": "demo-partial",
        "manufacturer": "Acme Imaging",
        "models": "DemoScope 2000",
    }
    base.update(overrides)
    row = [""] * _WIDTH
    for name, value in base.items():
        row[_FLAT_COLUMN_NAMES.index(name)] = value
    return row


def _leaf(field: str, value: str, profile_id: str = "demo-partial") -> list[str]:
    row = [""] * _WIDTH
    row[0] = "coordinate"
    row[1] = profile_id
    row[_FLAT_COLUMN_NAMES.index("field")] = field
    row[_FLAT_COLUMN_NAMES.index("value")] = value
    return row


_ALL_LEAVES = [
    _leaf("translation_offset.x", "0.0"),
    _leaf("translation_offset.y", "0.0"),
    _leaf("translation_offset.z", "0.0"),
    _leaf("translation_direction.x", "+"),
    _leaf("translation_direction.y", "-"),
    _leaf("translation_direction.z", "+"),
    _leaf("rotation_direction.Ap1", "+"),
    _leaf("rotation_direction.Ap2", "-"),
    _leaf("rotation_direction.Ap3", "+"),
    _leaf("rotation_direction.At1", "+"),
    _leaf("rotation_direction.At2", "-"),
    _leaf("rotation_direction.At3", "+"),
    _leaf("swap_lateral_longitudinal", "false"),
    _leaf("field_size_mode", "CFA"),
    _leaf("detector_side_length", "40"),
]

_LEAF_VALUES = [
    ("translation_offset.x", "0.0"),
    ("translation_offset.y", "0.0"),
    ("translation_offset.z", "0.0"),
    ("translation_direction.x", "+"),
    ("translation_direction.y", "-"),
    ("translation_direction.z", "+"),
    ("rotation_direction.Ap1", "+"),
    ("rotation_direction.Ap2", "-"),
    ("rotation_direction.Ap3", "+"),
    ("rotation_direction.At1", "+"),
    ("rotation_direction.At2", "-"),
    ("rotation_direction.At3", "+"),
    ("swap_lateral_longitudinal", "false"),
    ("field_size_mode", "CFA"),
    ("detector_side_length", "40"),
]


_TRANSMISSION_ROW: dict[str, str] = {
    "record_type": "transmission",
    "profile_id": "demo-partial",
    "device_model": "DemoScope 2000",
    "acquisition_plane": "Single Plane",
    "kvp_kv": "80",
    "filtration_added_mmcu": "0.0",
    "filtration_added_mmal": "0",
    "k_patient_support": "0.71",
    "evidence_status": "estimated",
    "date": "1901-01-01",
}


def _transmission_row(**overrides: str) -> list[str]:
    values = dict(_TRANSMISSION_ROW)
    values.update(overrides)
    row = [""] * _WIDTH
    for name, value in values.items():
        row[_FLAT_COLUMN_NAMES.index(name)] = value
    return row


def _tsv(csv_text: str) -> bytes:
    """Convert CSV text to TSV text in memory (no new fixture file)."""
    rows = list(csv.reader(io.StringIO(csv_text)))
    return "\n".join("\t".join(row) for row in rows).encode("utf-8")


# ---------------------------------------------------------------------------
# Canonical equivalence with the packaged JSON
# ---------------------------------------------------------------------------


def test_packaged_csv_equals_packaged_json_canonically() -> None:
    from_json = parse_json_bytes(_JSON_PATH.read_bytes())
    from_csv = parse_csv_bytes(_CSV_PATH.read_bytes())

    assert len(from_csv.profiles) == len(from_json.profiles)
    assert from_csv.logical_rows == from_json.logical_rows == 3 + 16 + 5
    for left, right in zip(from_json.profiles, from_csv.profiles, strict=True):
        assert left.profile_id == right.profile_id
        assert canonical_profile_dict(left) == canonical_profile_dict(right)
        assert profile_hash(left) == profile_hash(right)
        assert left.coordinate_leaves() == right.coordinate_leaves()
        assert tuple(row.key for row in left.transmission) == tuple(row.key for row in right.transmission)
    assert active_set_hash(from_json.profiles) == active_set_hash(from_csv.profiles)


def test_raw_source_hashes_differ_while_profile_hashes_match() -> None:
    from_json = parse_json_bytes(_JSON_PATH.read_bytes())
    from_csv = parse_csv_bytes(_CSV_PATH.read_bytes())

    assert from_json.source_hash != from_csv.source_hash
    assert from_csv.source_hash == source_bytes_hash(_CSV_PATH.read_bytes())
    assert from_json.source_hash == source_bytes_hash(_JSON_PATH.read_bytes())


def test_generated_tsv_matches_the_csv_profile_hashes() -> None:
    from_csv = parse_csv_bytes(_CSV_PATH.read_bytes())
    from_tsv = parse_tsv_bytes(_tsv(_CSV_PATH.read_text(encoding="utf-8")))

    assert from_tsv.source_kind == "tsv"
    assert from_csv.source_kind == "csv"
    assert [profile_hash(p) for p in from_tsv.profiles] == [profile_hash(p) for p in from_csv.profiles]
    assert from_tsv.logical_rows == from_csv.logical_rows


def test_csv_utf8_bom_is_accepted() -> None:
    raw = _CSV_PATH.read_bytes()
    document = parse_csv_bytes(b"\xef\xbb\xbf" + raw)

    assert len(document.profiles) == 3
    assert profile_hash(document.profiles[0]) == profile_hash(parse_csv_bytes(raw).profiles[0])


# ---------------------------------------------------------------------------
# Header rules
# ---------------------------------------------------------------------------


def test_reordered_columns_are_accepted() -> None:
    header = list(reversed(_FLAT_COLUMN_NAMES))
    rows = [_profile_row(), _leaf("translation_offset.x", "1.0")]
    index = {name: _FLAT_COLUMN_NAMES.index(name) for name in header}

    document = parse_csv_bytes(_write([[row[index[name]] for name in header] for row in rows], header=header))
    assert document.profiles[0].coordinates is not None
    assert document.profiles[0].coordinates.translation_offset is not None
    assert document.profiles[0].coordinates.translation_offset.x == 1.0


def test_optional_promotion_column_is_accepted_on_a_wildcard() -> None:
    header = [*_FLAT_COLUMN_NAMES, _PROMOTION_COLUMN]
    rows = [
        ["profile", "demo-wild", "Acme Imaging", "*"] + [""] * (_WIDTH - 4) + ["true"],
        _leaf("translation_offset.z", "-1.0", profile_id="demo-wild"),
    ]
    rows[0] = [*rows[0][:_WIDTH], "true"]
    rows[1] = [*rows[1][:_WIDTH], ""]

    document = parse_csv_bytes(_write([rows[0], rows[1]], header=header))
    assert document.profiles[0].models == ("*",)
    assert document.profiles[0].promote_coordinate_wildcard is True


def test_duplicate_header_column_is_rejected_without_echoing_it() -> None:
    header = [*_FLAT_COLUMN_NAMES, "notes"]
    payload = _write([_profile_row()], header=header)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_JSON_KEY
    assert "notes" not in repr(excinfo.value)


def test_unknown_header_column_is_rejected_without_echoing_it() -> None:
    header = [*_FLAT_COLUMN_NAMES, "not_a_column"]
    payload = _write([_profile_row()], header=header)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert "not_a_column" not in str(excinfo.value)
    assert "not_a_column" not in repr(excinfo.value)

def test_missing_header_column_is_rejected() -> None:
    payload = _write([_profile_row()], header=list(_FLAT_COLUMN_NAMES[:-1]))
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.MISSING_REQUIRED_FIELD


def test_promotion_value_without_the_column_is_a_width_error() -> None:
    payload = _write([[*_profile_row(), "true"]])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.MALFORMED_TABULAR


# ---------------------------------------------------------------------------
# Row rules
# ---------------------------------------------------------------------------


def test_short_and_long_rows_are_rejected() -> None:
    for rows in ([_profile_row()[:-1]], [[*_profile_row(), ""]]):
        payload = _write(rows)
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_csv_bytes(payload)
        assert _code(excinfo) is ProfileErrorCode.MALFORMED_TABULAR


def test_unknown_record_type_is_rejected_without_echoing_it() -> None:
    row = _profile_row()
    row[0] = "not-a-record-type"
    payload = _write([row])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert "not-a-record-type" not in str(excinfo.value)


def test_value_in_a_non_applicable_column_is_rejected() -> None:
    row = _leaf("translation_offset.x", "1.0")
    row[_FLAT_COLUMN_NAMES.index("acquisition_plane")] = "Single Plane"
    payload = _write([_profile_row(), row])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert excinfo.value.field_path == ("acquisition_plane",)


# ---------------------------------------------------------------------------
# Grouping and ordering
# ---------------------------------------------------------------------------


def test_coordinate_and_transmission_rows_may_precede_their_profile_row() -> None:
    rows = [*_ALL_LEAVES, _transmission_row(), _profile_row()]
    document = parse_csv_bytes(_write(rows))

    assert len(document.profiles) == 1
    assert len(document.profiles[0].coordinate_leaves()) == 15
    assert len(document.profiles[0].transmission) == 1


def test_orphan_rows_without_required_metadata_fail() -> None:
    for rows in ([*_ALL_LEAVES], [_transmission_row()]):
        payload = _write(rows)
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_csv_bytes(payload)
        assert _code(excinfo) is ProfileErrorCode.MISSING_REQUIRED_FIELD


def test_repeated_profile_metadata_may_agree() -> None:
    document = parse_csv_bytes(_write([_profile_row(), _profile_row(), *_ALL_LEAVES]))
    assert len(document.profiles) == 1


def test_conflicting_repeated_metadata_fails() -> None:
    rows = [_profile_row(), _profile_row(models="DemoScope 3000"), *_ALL_LEAVES]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.CONFLICTING_PROFILE_METADATA


def test_duplicate_coordinate_leaf_fails_even_when_identical() -> None:
    rows = [_profile_row(), *_ALL_LEAVES, _leaf("translation_offset.x", "0.0")]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_JSON_KEY


def test_duplicate_transmission_key_fails_through_the_canonical_check() -> None:
    rows = [_profile_row(), _transmission_row(), _transmission_row()]
    parsed = [parse_csv_bytes(_write(rows))]
    with pytest.raises(EquipmentProfileError) as excinfo:
        combine_documents(parsed)

    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY


def test_rows_are_counted_as_logical_rows() -> None:
    rows = [_profile_row(), *_ALL_LEAVES, _transmission_row()]
    document = parse_csv_bytes(_write(rows))
    assert document.logical_rows == 1 + 15 + 1


# ---------------------------------------------------------------------------
# Alias cell forms
# ---------------------------------------------------------------------------


def test_pipe_separated_shorthand_list_is_accepted() -> None:
    rows = [_profile_row(model_aliases="DemoScope2000|DS2000"), *_ALL_LEAVES]
    document = parse_csv_bytes(_write(rows))

    assert document.profiles[0].model_aliases == (
        ("DemoScope2000", "DemoScope 2000"),
        ("DS2000", "DemoScope 2000"),
    )


def test_pipe_list_with_multiple_models_is_ambiguous() -> None:
    rows = [_profile_row(models="A|B", model_aliases="x"), *_ALL_LEAVES]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET


def test_quoted_json_alias_map_cell_is_accepted() -> None:
    rows = [
        _profile_row(models="A|B", model_aliases='{"x": "A", "y": "B"}'),
        *_ALL_LEAVES,
    ]
    document = parse_csv_bytes(_write(rows))

    assert document.profiles[0].model_aliases == (("x", "A"), ("y", "B"))


def test_map_target_must_be_a_listed_model() -> None:
    rows = [_profile_row(model_aliases='{"x": "Unlisted"}'), *_ALL_LEAVES]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.ALIAS_TARGET_MISMATCH


def test_malformed_json_alias_map_cell_is_rejected() -> None:
    rows = [_profile_row(model_aliases='{"x": '), *_ALL_LEAVES]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.MALFORMED_TABULAR


def test_duplicate_key_in_a_json_alias_map_cell_is_rejected() -> None:
    rows = [_profile_row(model_aliases='{"x": "A", "x": "B"}'), *_ALL_LEAVES]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_JSON_KEY


def test_csv_alias_map_equals_json_alias_map_content() -> None:
    flat = parse_csv_bytes(
        _write([_profile_row(models="A|B", model_aliases='{"x": "A", "y": "B"}'), *_ALL_LEAVES])
    ).profiles[0]
    nested = parse_json_bytes(
        json.dumps(
            {
                "schema_version": 1,
                "profiles": [
                    {
                        "profile_id": "demo-partial",
                        "manufacturer": "Acme Imaging",
                        "models": ["A", "B"],
                        "model_aliases": {"x": "A", "y": "B"},
                        "coordinates": {
                            "translation_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "translation_direction": {"x": "+", "y": "-", "z": "+"},
                            "rotation_direction": {
                                "Ap1": "+", "Ap2": "-", "Ap3": "+",
                                "At1": "+", "At2": "-", "At3": "+",
                            },
                            "swap_lateral_longitudinal": False,
                            "field_size_mode": "CFA",
                            "detector_side_length": 40,
                        },
                    }
                ],
            }
        ).encode("utf-8")
    ).profiles[0]

    assert profile_hash(flat) == profile_hash(nested)


# ---------------------------------------------------------------------------
# Required cells, blanks, numbers, booleans
# ---------------------------------------------------------------------------


def test_blank_required_profile_cells_fail() -> None:
    for column in ("manufacturer", "models", "profile_id"):
        payload = _write([_profile_row(**{column: ""}), *_ALL_LEAVES])
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_csv_bytes(payload)
        assert _code(excinfo) is ProfileErrorCode.BLANK_REQUIRED_CELL, column
        assert excinfo.value.field_path == (column,)


def test_blank_filtration_is_disallowed_not_read_as_zero() -> None:
    for column in ("filtration_added_mmcu", "filtration_added_mmal"):
        payload = _write([_profile_row(), _transmission_row(**{column: ""})])
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_csv_bytes(payload)
        assert _code(excinfo) is ProfileErrorCode.BLANK_DISALLOWED_CELL, column
        assert excinfo.value.field_path == (column,)


def test_explicit_zero_filtration_is_accepted() -> None:
    document = parse_csv_bytes(
        _write([_profile_row(), _transmission_row(filtration_added_mmcu="0", filtration_added_mmal="0")])
    )
    assert document.profiles[0].transmission[0].filtration_added_mmcu == 0.0


def test_non_finite_and_boolean_numeric_cells_are_rejected() -> None:
    for value in ("NaN", "nan", "inf", "-inf", "Infinity", "1e999", "true", "false", "8_0", "abc", ""):
        payload = _write([_profile_row(), _transmission_row(kvp_kv=value)])
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_csv_bytes(payload)
        assert _code(excinfo) in (
            ProfileErrorCode.INVALID_NUMBER,
            ProfileErrorCode.BLANK_REQUIRED_CELL,
        ), value


def test_huge_integer_is_rejected_as_non_finite() -> None:
    payload = _write([_profile_row(), _transmission_row(kvp_kv="1" + "0" * 400)])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.INVALID_NUMBER


def test_only_true_and_false_are_boolean_lexical_forms() -> None:
    for value in ("True", "TRUE", "1", "0", "yes"):
        payload = _write([_profile_row(), _leaf("swap_lateral_longitudinal", value)])
        with pytest.raises(EquipmentProfileError) as excinfo:
            parse_csv_bytes(payload)
        assert _code(excinfo) is ProfileErrorCode.INVALID_TYPE, value


def test_bare_boolean_forms_are_accepted() -> None:
    document = parse_csv_bytes(
        _write([_profile_row(), _leaf("swap_lateral_longitudinal", "true")])
    )
    assert document.profiles[0].coordinates is not None
    assert document.profiles[0].coordinates.swap_lateral_longitudinal is True


def test_null_like_strings_are_literal_text_not_omission() -> None:
    document = parse_csv_bytes(_write([_profile_row(**{"source": "null"}), *_ALL_LEAVES]))
    assert document.profiles[0].provenance is not None
    assert document.profiles[0].provenance.source == "null"


def test_blank_coordinate_value_is_a_required_cell_error() -> None:
    payload = _write([_profile_row(), _leaf("translation_offset.x", "")])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.BLANK_REQUIRED_CELL
    assert excinfo.value.field_path == ("value",)


def test_unknown_leaf_name_is_rejected_without_echoing_it() -> None:
    payload = _write([_profile_row(), _leaf("translation_offset.w", "1.0")])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert excinfo.value.field_path == ("field",)
    assert "translation_offset.w" not in str(excinfo.value)
    assert "translation_offset.w" not in repr(excinfo.value)


def test_unknown_non_dotted_field_is_rejected() -> None:
    payload = _write([_profile_row(), _leaf("nonsense_field", "1.0")])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD
    assert "nonsense_field" not in str(excinfo.value)


def test_sign_leaf_rejects_other_literals() -> None:
    payload = _write([_profile_row(), _leaf("translation_direction.x", "xx")])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.INVALID_ENUM


def test_measured_rows_require_source_and_date() -> None:
    # A blank optional cell is read as "omitted", so measured-without-source is a missing-field error.
    payload = _write([_profile_row(), _transmission_row(evidence_status="measured", date="2026-01-01")])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(
            payload
        )
    assert _code(excinfo) is ProfileErrorCode.MISSING_REQUIRED_FIELD

    payload = _write(
                [
                    _profile_row(),
                    _transmission_row(evidence_status="measured", source="physicist", date=""),
                ]
            )
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(
            payload
        )
    assert _code(excinfo) is ProfileErrorCode.MISSING_REQUIRED_FIELD


def test_measured_date_must_be_strict() -> None:
    rows = [
        _profile_row(),
        _transmission_row(evidence_status="measured", source="physicist", date="2026-02-30"),
    ]
    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)
    assert _code(excinfo) is ProfileErrorCode.INVALID_DATE


def test_promotion_is_rejected_without_a_wildcard_model() -> None:
    header = [*_FLAT_COLUMN_NAMES, _PROMOTION_COLUMN]
    row = _profile_row()
    row.append("true")
    payload = _write([row], header=header)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.WILDCARD_NOT_PERMITTED


# ---------------------------------------------------------------------------
# Bounds and file handling
# ---------------------------------------------------------------------------


def test_oversized_source_is_rejected_by_the_bounded_read(tmp_path: Path) -> None:
    target = tmp_path / "too_big.csv"
    target.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))

    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_file(target)
    assert _code(excinfo) is ProfileErrorCode.OVERSIZED_SOURCE
    assert str(target) not in str(excinfo.value)


def test_csv_file_adapter_uses_the_csv_source_kind_on_every_error(tmp_path: Path) -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_file(tmp_path / "missing.csv")
    assert excinfo.value.source_kind == "csv"
    assert _code(excinfo) is ProfileErrorCode.UNREADABLE_SOURCE

    wrong = tmp_path / "profiles.json"
    wrong.write_bytes(b"{}")
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_file(wrong)
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX
    assert excinfo.value.source_kind == "csv"


def test_tsv_file_adapter_uses_the_tsv_source_kind(tmp_path: Path) -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_tsv_file(tmp_path / "missing.tsv")
    assert excinfo.value.source_kind == "tsv"

    wrong = tmp_path / "profiles.csv"
    wrong.write_bytes(b"x")
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_tsv_file(wrong)
    assert _code(excinfo) is ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX
    assert excinfo.value.source_kind == "tsv"


def test_wrong_delimiter_is_a_header_error() -> None:
    text = _CSV_PATH.read_text(encoding="utf-8").replace(",", ";")
    payload = text.encode("utf-8")
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_tsv_bytes(payload)
    assert _code(excinfo) is ProfileErrorCode.UNKNOWN_FIELD


def test_aggregate_row_ceiling_is_enforced_before_materialization() -> None:
    """A document whose logical rows exceed the ceiling is rejected while accumulating rows.

    Five fully populated profiles (1 profile row + 15 coordinate leaves + 2000 transmission rows each) reach
    ``5 * 2016 = 10_080`` logical rows, so the ceiling is the first failure rather than any per-profile rule.
    """
    rows: list[list[str]] = []
    planes = ("Single Plane", "Plane A", "Plane B")
    for index in range(5):
        profile_id = f"demo-partial-{index}"
        model = f"Model {index}"
        rows.append(_profile_row(profile_id=profile_id, models=model))
        rows.extend(_leaf(field, value, profile_id=profile_id) for field, value in _LEAF_VALUES)
        for offset in range(2_000):
            rows.append(
                _transmission_row(
                    profile_id=profile_id,
                    device_model=model,
                    acquisition_plane=planes[offset % 3],
                    filtration_added_mmal=str(offset % 1_000),
                )
            )
    assert len(rows) == 5 * (1 + 15 + 2_000)

    payload = _write(rows)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)

    assert _code(excinfo) is ProfileErrorCode.ROW_LIMIT_EXCEEDED


def test_empty_source_is_rejected() -> None:
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(b"")
    assert _code(excinfo) is ProfileErrorCode.EMPTY_SOURCE
    assert excinfo.value.source_kind == "csv"


# ---------------------------------------------------------------------------
# Cross-file duplicates
# ---------------------------------------------------------------------------


def test_same_profile_in_two_files_still_fails() -> None:
    document = parse_csv_bytes(_CSV_PATH.read_bytes())
    with pytest.raises(EquipmentProfileError) as excinfo:
        combine_documents([document, document])

    assert _code(excinfo) is ProfileErrorCode.DUPLICATE_PROFILE_ID


def test_errors_never_leak_raw_cells() -> None:
    header = [*_FLAT_COLUMN_NAMES, "top_secret_column"]
    payload = _write([_profile_row()], header=header)
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)
    assert "top_secret_column" not in str(excinfo.value)
    assert "top_secret_column" not in repr(excinfo.value)

    row = _profile_row()[:-1]
    payload = _write([row])
    with pytest.raises(EquipmentProfileError) as excinfo:
        parse_csv_bytes(payload)
    assert "Acme" not in str(excinfo.value)


@pytest.mark.parametrize("delimiter", [",", "\t"])
def test_unclosed_quote_is_malformed(delimiter: str) -> None:
    from guiskindose.equipment_profiles.tabular_common import tabular_rows

    rows_iter = tabular_rows('"unfinished', delimiter=delimiter, source_kind="csv" if delimiter == "," else "tsv")
    with pytest.raises(EquipmentProfileError) as excinfo:
        list(rows_iter)
    assert excinfo.value.code == ProfileErrorCode.MALFORMED_TABULAR
    assert "unfinished" not in str(excinfo.value)
    assert excinfo.value.__suppress_context__


@pytest.mark.parametrize("parser,suffix", [(parse_csv_file, ".csv"), (parse_tsv_file, ".tsv")])
def test_invalid_path_is_value_free(parser: object, suffix: str) -> None:
    read = parse_csv_file if parser is parse_csv_file else parse_tsv_file
    with pytest.raises(EquipmentProfileError) as excinfo:
        read("invalid\x00" + suffix)
    assert excinfo.value.code == ProfileErrorCode.UNREADABLE_SOURCE
    assert "invalid" not in str(excinfo.value)
