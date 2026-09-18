"""Tests for the packaged correction-data provider and source resolution."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from guiskindose import load_settings_example_json
from guiskindose.correction_data import (
    CorrectionDataError,
    clear_cache,
    explicit_table,
    get_table,
    packaged_source_hash,
    reset_warnings,
    resolve_corrections_source,
)
from guiskindose.geom_calc import fetch_and_append_hvl
from guiskindose.settings import PyskindoseSettings

TABLE_DIR = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "table_data"

RUNTIME_TABLES = ("hvl_combined", "correction_medium_and_backscatter", "correction_table_and_pad_attenuation")


@pytest.fixture(autouse=True)
def _fresh_provider_state():
    clear_cache()
    reset_warnings()
    yield
    clear_cache()
    reset_warnings()


def _csv_frame(name: str) -> pd.DataFrame:
    files = {
        "hvl_combined": "hvl_tables/hvl_combined.csv",
        "correction_medium_and_backscatter": "correction_medium_and_backscatter.csv",
        "correction_table_and_pad_attenuation": "correction_table_and_pad_attenuation.csv",
        "device_info": "device_info.csv",
    }
    return pd.read_csv(TABLE_DIR / files[name])


def test_get_table_matches_csv_bytes():
    for name in RUNTIME_TABLES:
        pd.testing.assert_frame_equal(get_table(name), _csv_frame(name))


def test_get_table_unknown_raises():
    with pytest.raises(KeyError):
        get_table("nope")


def test_get_table_returns_isolated_copies():
    first = get_table("hvl_combined")
    first.loc[0, "hvl_mmal"] = -1.0
    assert get_table("hvl_combined").loc[0, "hvl_mmal"] != -1.0


def test_packaged_hash_deterministic_hex():
    first, second = packaged_source_hash(), packaged_source_hash()
    assert first == second and len(first) == 64 and int(first, 16) >= 0


def test_resolve_defaults_to_packaged():
    assert resolve_corrections_source(None) == ("packaged", None)
    assert resolve_corrections_source("") == ("packaged", None)
    assert resolve_corrections_source("   ") == ("packaged", None)
    assert resolve_corrections_source("corrections.db") == ("packaged", None)


def test_resolve_explicit_and_warns_once(recwarn: pytest.WarningsRecorder):
    source, path = resolve_corrections_source("custom.db")
    assert source == "explicit" and str(path) == "custom.db"
    source, path = resolve_corrections_source("/abs/custom.db")
    assert source == "explicit" and path is not None and path.is_absolute()
    assert len([w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]) == 2
    resolve_corrections_source("other.db")
    assert len([w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]) == 2


def test_resolve_tilde_rejected_with_hint():
    with pytest.raises(ValueError, match="absolute"):
        resolve_corrections_source("~/custom.db")


def test_resolve_emit_warnings_false_is_silent(recwarn: pytest.WarningsRecorder):
    resolve_corrections_source("custom.db", emit_warnings=False)
    assert [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)] == []


def _legacy_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    for name in (*RUNTIME_TABLES, "device_info"):
        _csv_frame(name).to_sql(name, conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


def test_explicit_parity_with_packaged(tmp_path: Path):
    db = tmp_path / "legacy.db"
    _legacy_db(db)
    for name in RUNTIME_TABLES:
        pd.testing.assert_frame_equal(explicit_table(db, name).reset_index(drop=True), get_table(name).reset_index(drop=True))


def test_explicit_malformed_fails_value_free(tmp_path: Path):
    db = tmp_path / "bad.db"
    db.write_bytes(b"not sqlite")
    with pytest.raises(CorrectionDataError) as excinfo:
        explicit_table(db, "hvl_combined")
    assert str(tmp_path) not in str(excinfo.value)


def test_sentinel_db_ignored_and_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sentinel = tmp_path / "corrections.db"
    conn = sqlite3.connect(sentinel)
    conn.execute("CREATE TABLE hvl_combined (kvp_kv REAL)")
    conn.execute("INSERT INTO hvl_combined VALUES (1.0)")
    conn.commit()
    conn.close()
    before = sentinel.read_bytes()
    monkeypatch.chdir(tmp_path)
    assert resolve_corrections_source("corrections.db") == ("packaged", None)
    assert len(get_table("hvl_combined")) == 65534
    assert sentinel.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} == {"corrections.db"}


def test_default_lookup_creates_no_cwd_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({"kVp": [70.0], "filter_thickness_Cu": [0.0], "filter_thickness_Al": [0.0]})
    out = fetch_and_append_hvl(data_norm=frame, inherent_filtration=2.5, corrections_db="corrections.db")
    assert "HVL" in out.columns and out["HVL"].notna().all()
    assert list(tmp_path.iterdir()) == []


def test_export_descriptor_has_no_paths(tmp_path: Path):
    from guiskindose.export.sections import non_default_settings, serialize_settings

    base = load_settings_example_json()
    settings = PyskindoseSettings(settings=dict(base), output_format="dict")
    snap = serialize_settings(settings)
    assert snap["corrections_db_path"] == "packaged"
    assert snap["corrections_db_source"]["source"] == "packaged-csv"
    assert len(snap["corrections_db_source"]["sha256"]) == 64
    assert non_default_settings(snap).get("corrections_db_path") is None
    payload = json.dumps(snap, default=str)
    assert ".db" not in payload

    db = tmp_path / "deep" / "custom.db"
    db.parent.mkdir()
    _legacy_db(db)
    explicit = PyskindoseSettings(settings={**base, "corrections_db_path": str(db)}, output_format="dict")
    snap2 = serialize_settings(explicit)
    assert snap2["corrections_db_path"] == "explicit"
    assert snap2["corrections_db_source"]["source"] == "explicit-sqlite"
    assert len(snap2["corrections_db_source"]["sha256"]) == 64
    payload2 = json.dumps(snap2, default=str)
    assert str(tmp_path) not in payload2 and ".db" not in payload2
