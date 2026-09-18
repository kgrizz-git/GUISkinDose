"""Tests for the correction-data manifest: coverage, hashes, and de-identification."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from guiskindose.correction_validation import check_manifest_consistency, load_manifest

TABLE_DIR = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "table_data"

REAL_SERIALS = {"146278", "146936", "722010564", "722013362"}
REAL_LABS = {"U105", "U106", "U601", "U104"}


def _errors(manifest: dict, table_dir: Path = TABLE_DIR):
    return [i for i in check_manifest_consistency(manifest, table_dir) if i.severity == "error"]


def test_manifest_parses_with_version_and_tables():
    manifest = load_manifest(TABLE_DIR)
    assert manifest["manifest_version"] == 1
    assert len(manifest["tables"]) == 6


def test_shipped_manifest_is_consistent_with_shipped_csvs():
    assert _errors(load_manifest(TABLE_DIR)) == []


def test_every_csv_is_covered_and_hashed():
    manifest = load_manifest(TABLE_DIR)
    by_file = {entry["file"]: entry for entry in manifest["tables"]}
    assert set(by_file) == {
        "correction_medium_and_backscatter.csv",
        "correction_table_and_pad_attenuation.csv",
        "device_info.csv",
        "hvl_tables/hvl_allura_filters_11deg.csv",
        "hvl_tables/hvl_axiom_filters_8deg.csv",
        "hvl_tables/hvl_combined.csv",
    }
    for entry in manifest["tables"]:
        assert len(entry["sha256"]) == 64


def test_runtime_tables_name_consumers_and_build_inputs_do_not():
    manifest = load_manifest(TABLE_DIR)
    for entry in manifest["tables"]:
        if entry["role"] == "runtime_lookup":
            assert entry["runtime_consumer"], entry["file"]
        else:
            assert entry["runtime_consumer"] is None, entry["file"]


def test_unread_columns_are_flagged_not_implied():
    text = (TABLE_DIR / "correction_data_manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(text)
    by_file = {entry["file"]: entry for entry in manifest["tables"]}
    medium = {col["name"]: col for col in by_file["correction_medium_and_backscatter.csv"]["columns"]}
    assert medium["h"]["runtime_read"] is False
    assert medium["backscatter"]["runtime_read"] is False
    vendor = by_file["hvl_tables/hvl_allura_filters_11deg.csv"]
    assert vendor["role"] == "build_input"
    assert all(col["runtime_read"] is False for col in vendor["columns"])


def test_tampered_csv_fails_hash_check(tmp_path: Path):
    import shutil

    for name in ("correction_medium_and_backscatter.csv",):
        shutil.copy(TABLE_DIR / name, tmp_path / name)
    manifest = load_manifest(TABLE_DIR)
    trimmed = {"tables": [e for e in manifest["tables"] if e["file"] == "correction_medium_and_backscatter.csv"]}
    with (tmp_path / "correction_medium_and_backscatter.csv").open("a", encoding="utf-8") as fh:
        fh.write("50,2.5,0,2.0,1.0,5,1.2,1.02\n")
    codes = {i.code for i in _errors(trimmed, tmp_path)}
    assert "hash_mismatch" in codes


def test_manifest_columns_match_csv_headers(tmp_path: Path):
    import shutil

    name = "device_info.csv"
    shutil.copy(TABLE_DIR / name, tmp_path / name)
    manifest = load_manifest(TABLE_DIR)
    trimmed = {"tables": [dict(e) for e in manifest["tables"] if e["file"] == name]}
    assert _errors(trimmed, tmp_path) == []
    # A phantom column (the exact bug class that shipped in the attenuation
    # entry) must fail loudly instead of passing silently.
    trimmed["tables"][0]["columns"] = [*trimmed["tables"][0]["columns"], {"name": "phantom_col"}]
    codes = {i.code for i in _errors(trimmed, tmp_path)}
    assert "column_mismatch" in codes


def test_manifest_lookup_keys_must_be_declared_columns(tmp_path: Path):
    import shutil

    name = "device_info.csv"
    shutil.copy(TABLE_DIR / name, tmp_path / name)
    manifest = load_manifest(TABLE_DIR)
    trimmed = {"tables": [dict(e) for e in manifest["tables"] if e["file"] == name]}
    trimmed["tables"][0]["lookup_keys"] = ["Lab"]
    trimmed["tables"][0]["lookup_value"] = "PadThickness_mm"
    assert _errors(trimmed, tmp_path) == []
    trimmed["tables"][0]["lookup_keys"] = ["Nope"]
    assert "column_mismatch" in {i.code for i in _errors(trimmed, tmp_path)}
    trimmed["tables"][0]["lookup_keys"] = []
    trimmed["tables"][0]["lookup_value"] = "Nope"
    assert "column_mismatch" in {i.code for i in _errors(trimmed, tmp_path)}


def test_manifest_entry_without_file_field_fails(tmp_path: Path):
    manifest = {"tables": [{"role": "provenance_only"}]}
    codes = {i.code for i in _errors(manifest, tmp_path)}
    assert "missing_key" in codes


def test_device_info_carries_no_real_identifiers():
    rows = list(csv.DictReader((TABLE_DIR / "device_info.csv").open(encoding="utf-8")))
    assert [r["DeviceObserverSerialNumber"] for r in rows] == ["SYN-SN-01", "SYN-SN-02", "SYN-SN-03", "SYN-SN-04"]
    assert [r["Lab"] for r in rows] == ["SYN-LAB-A", "SYN-LAB-B", "SYN-LAB-C", "SYN-LAB-D"]
    cells = [value for row in rows for value in row.values() if value]
    assert not (REAL_SERIALS & set(cells))
    assert not (REAL_LABS & set(cells))
    assert [r["PadThickness_mm"] for r in rows] == ["74", "74", "101", "68"]
    assert [r["DateMeasured"] for r in rows] == ["2018-04", "", "2018-04", "2018-04"]
    # Row 3 references another row's lab: the token must match that lab's own row.
    by_lab = {r["Lab"]: r for r in rows}
    assert "SYN-LAB-A" in rows[1]["Comment"]
    assert by_lab["SYN-LAB-A"]["PadThickness_mm"] == "74"
