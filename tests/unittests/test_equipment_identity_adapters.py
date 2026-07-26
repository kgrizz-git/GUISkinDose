"""Phase 0: tabular adapters preserve per-unit equipment identity."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mypyskindose import load_settings_example_json
from mypyskindose.constants import (
    KEY_NORMALIZATION_DEVICE_SERIAL,
    KEY_NORMALIZATION_STATION_NAME,
)
from mypyskindose.settings import PyskindoseSettings

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabular_inputs"


def _default_settings() -> PyskindoseSettings:
    """Return example settings for tabular adapter tests."""
    return PyskindoseSettings(settings=load_settings_example_json())


def test_dosetrack_persists_equipment_name_as_station_name(tmp_path: Path):
    """DoseTrack Equipment Name is stored as station_name."""
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    result = read_and_normalize_input(
        FIXTURES / "dosetrack_events.csv",
        input_schema="dosetrack",
        settings=_default_settings(),
    )
    assert KEY_NORMALIZATION_STATION_NAME in result.normalized_data.columns
    assert (result.normalized_data[KEY_NORMALIZATION_STATION_NAME] == "AXIOM-Artis").all()
    # Model inference must remain intact.
    assert (result.normalized_data["model"] == "AXIOM-Artis").all()


def test_radimetrics_equipment_vs_device_split(tmp_path: Path):
    """Equipment → station_name; Device → model (never swapped)."""
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    src = FIXTURES / "radimetrics_events.csv"
    df = pd.read_csv(src)
    df.insert(1, "Equipment", "unit-rm-01")
    path = tmp_path / "radimetrics_with_equipment.csv"
    df.to_csv(path, index=False)

    result = read_and_normalize_input(
        path,
        input_schema="radimetrics",
        settings=_default_settings(),
    )
    assert (result.normalized_data[KEY_NORMALIZATION_STATION_NAME] == "unit-rm-01").all()
    assert (result.normalized_data["model"] == "AXIOM-Artis").all()


def test_radimetrics_without_equipment_station_is_none():
    """Radimetrics without Equipment leaves station_name null."""
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    result = read_and_normalize_input(
        FIXTURES / "radimetrics_events.csv",
        input_schema="radimetrics",
        settings=_default_settings(),
    )
    # No Equipment column → station_name column present but all-null / absent values.
    assert KEY_NORMALIZATION_STATION_NAME in result.normalized_data.columns
    assert result.normalized_data[KEY_NORMALIZATION_STATION_NAME].isna().all() or all(
        v is None or (isinstance(v, float) and pd.isna(v))
        for v in result.normalized_data[KEY_NORMALIZATION_STATION_NAME]
    )
    assert (result.normalized_data["model"] == "AXIOM-Artis").all()


def test_generic_rdsr_equipment_column_to_station(tmp_path: Path):
    """Generic RDSR Equipment column maps to station_name."""
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    src = FIXTURES / "generic_rdsr_events.csv"
    df = pd.read_csv(src)
    df["Equipment"] = "unit-gen-01"
    path = tmp_path / "generic_with_equipment.csv"
    df.to_csv(path, index=False)

    result = read_and_normalize_input(
        path,
        input_schema="generic_rdsr_like",
        settings=_default_settings(),
    )
    assert (result.normalized_data[KEY_NORMALIZATION_STATION_NAME] == "unit-gen-01").all()
    assert (result.normalized_data["model"] == "AXIOM-Artis").all()


def test_normalized_station_serial_round_trip(tmp_path: Path):
    """Normalized schema preserves station_name and device_serial."""
    from mypyskindose.input_adapters.models import InputAdapterResult
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    src = FIXTURES / "normalized_events.csv"
    df = pd.read_csv(src)
    df["station_name"] = "unit-norm-01"
    df["device_serial"] = "serial-norm-01"
    path = tmp_path / "normalized_with_identity.csv"
    df.to_csv(path, index=False)

    result = read_and_normalize_input(path, input_schema="normalized")
    assert isinstance(result, InputAdapterResult)
    assert (result.normalized_data[KEY_NORMALIZATION_STATION_NAME] == "unit-norm-01").all()
    assert (result.normalized_data[KEY_NORMALIZATION_DEVICE_SERIAL] == "serial-norm-01").all()


def test_normalized_without_identity_still_loads():
    """Normalized files without identity columns still load."""
    from mypyskindose.input_adapters.models import InputAdapterResult
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    result = read_and_normalize_input(
        FIXTURES / "normalized_events.csv",
        input_schema="normalized",
    )
    assert isinstance(result, InputAdapterResult)
    assert "K_IRP" in result.normalized_data.columns
    assert KEY_NORMALIZATION_STATION_NAME not in result.normalized_data.columns
