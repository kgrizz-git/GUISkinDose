"""Dose-pipeline tests for kerma-meter correction (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest

from mypyskindose import constants as c
from mypyskindose import load_settings_example_json
from mypyskindose.calculate_dose.calculate_dose import calculate_dose
from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from mypyskindose.phantom_class import Phantom
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

EXAMPLE = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "example_data" / "RDSR"


def _settings(**km_overrides) -> PyskindoseSettings:
    """Build calculate_dose settings with optional kerma-meter overrides."""
    raw = load_settings_example_json()
    raw["mode"] = "calculate_dose"
    raw["phantom"]["model"] = "cylinder"
    raw["plot"]["notebook_mode"] = False
    raw["plot"]["plot_dosemap"] = False
    raw["silence_pydicom_warnings"] = True
    km = raw.setdefault("kerma_meter_correction", {})
    km.update(km_overrides)
    return PyskindoseSettings(settings=raw)


def _table_pad(settings: PyskindoseSettings) -> tuple[Phantom, Phantom]:
    """Construct table and pad phantoms for a settings object."""
    dim = settings.phantom.dimension
    return (
        Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=dim),
        Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=dim),
    )


def _norm_from_example(name: str, settings: PyskindoseSettings):
    """Parse and normalize an example RDSR, appending rotation matrices."""
    data_raw = pydicom.dcmread(EXAMPLE / name)
    norm = rdsr_normalizer(rdsr_parser(data_raw, silence_pydicom_warnings=True), settings)
    return calculate_rotation_matrices(norm)


def test_disabled_matches_baseline_psd():
    """CF disabled matches enable+default_factor=1.0 dose maps and kerma."""
    settings = _settings(enable=False)
    data_norm = _norm_from_example("siemens_axiom_artis.dcm", settings)
    table, pad = _table_pad(settings)
    _, out_off, _ = calculate_dose(data_norm.copy(), settings, table, pad)

    settings_on = _settings(enable=True, default_factor=1.0, file=None)
    table2, pad2 = _table_pad(settings_on)
    _, out_on, _ = calculate_dose(data_norm.copy(), settings_on, table2, pad2)

    assert out_off is not None and out_on is not None
    assert np.allclose(out_off[c.OUTPUT_KEY_DOSE_MAP], out_on[c.OUTPUT_KEY_DOSE_MAP])
    assert out_on[c.OUTPUT_KEY_KERMA] == pytest.approx(out_off[c.OUTPUT_KEY_KERMA])
    assert out_on[c.OUTPUT_KEY_KERMA_CORRECTED] == pytest.approx(out_on[c.OUTPUT_KEY_KERMA])


def test_constant_cf_scales_psd_and_preserves_reported_kerma():
    """Table CF scales dose/corrected kerma while reported kerma stays unchanged."""
    settings = _settings(enable=False)
    data_norm = _norm_from_example("siemens_axiom_artis.dcm", settings)
    table, pad = _table_pad(settings)
    _, out_base, _ = calculate_dose(data_norm.copy(), settings, table, pad)

    # Distinct default_factor so a missed lookup cannot silently look correct.
    settings_cf = _settings(enable=True, default_factor=2.0, file=None)
    settings_cf.kerma_meter_correction.in_memory_table = {("146278", "single"): 1.5}
    table2, pad2 = _table_pad(settings_cf)
    k_irp_before = data_norm[c.KEY_NORMALIZATION_AIR_KERMA].tolist()
    _, out_cf, _ = calculate_dose(data_norm.copy(), settings_cf, table2, pad2)

    assert out_base is not None and out_cf is not None
    assert data_norm[c.KEY_NORMALIZATION_AIR_KERMA].tolist() == pytest.approx(k_irp_before)
    assert out_cf[c.OUTPUT_KEY_KERMA] == pytest.approx(out_base[c.OUTPUT_KEY_KERMA])
    expected_corrected = [k * 1.5 for k in out_base[c.OUTPUT_KEY_KERMA]]
    assert out_cf[c.OUTPUT_KEY_KERMA_CORRECTED] == pytest.approx(expected_corrected)
    assert out_cf[c.OUTPUT_KEY_CORRECTION_KERMA_METER] == pytest.approx([1.5] * len(out_cf[c.OUTPUT_KEY_KERMA]))
    # Physics corrections unchanged.
    assert out_cf[c.OUTPUT_KEY_CORRECTION_TABLE] == pytest.approx(out_base[c.OUTPUT_KEY_CORRECTION_TABLE])
    assert np.allclose(out_cf[c.OUTPUT_KEY_DOSE_MAP], out_base[c.OUTPUT_KEY_DOSE_MAP] * 1.5)


def test_settings_round_trip_without_block():
    """Settings JSON without kerma_meter_correction still loads with safe defaults."""
    raw = load_settings_example_json()
    raw.pop("kerma_meter_correction", None)
    settings = PyskindoseSettings(settings=raw)
    assert settings.kerma_meter_correction.enable is False
    assert settings.kerma_meter_correction.default_factor == pytest.approx(1.0)


def test_settings_example_block_loads():
    """settings_example.json kerma_meter_correction block parses as expected."""
    settings = PyskindoseSettings(settings=load_settings_example_json())
    assert settings.kerma_meter_correction.enable is False
    assert settings.kerma_meter_correction.mode == "file"


def test_kerma_settings_validation_and_to_dict(tmp_path: Path):
    """Settings reject bad mode/default_factor and serialize without in_memory_table."""
    from mypyskindose.settings.kerma_meter_correction_settings import (
        KermaMeterCorrectionSettings,
    )

    with pytest.raises(ValueError, match="mode must be"):
        KermaMeterCorrectionSettings({"mode": "auto"})
    with pytest.raises(ValueError, match="default_factor"):
        KermaMeterCorrectionSettings({"default_factor": 0.0})

    cf = tmp_path / "cf.csv"
    km = KermaMeterCorrectionSettings(
        {
            "enable": True,
            "mode": "prompt",
            "file": str(cf),
            "file_sheet": "Sheet1",
            "default_factor": 3.0,
            "explicit_label": "lab-1",
            "prompt_at_calc": True,
            "in_memory_table": {("a", "single"): 1.1},
        }
    )
    assert km.file == cf
    assert km.file_sheet == "Sheet1"
    assert km.explicit_label == "lab-1"
    assert km.default_factor == pytest.approx(3.0)
    assert km.in_memory_table == {("a", "single"): 1.1}
    payload = km.to_dict()
    assert payload["enable"] is True
    assert payload["mode"] == "prompt"
    assert payload["file"] == str(cf)
    assert "in_memory_table" not in payload
