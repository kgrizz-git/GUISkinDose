"""Dose-pipeline tests for kerma-meter correction (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from guiskindose.phantom_class import Phantom
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

EXAMPLE = Path(__file__).resolve().parents[2] / "src" / "guiskindose" / "example_data" / "RDSR"


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

    assert out_off is not None
    assert out_on is not None
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

    assert out_base is not None
    assert out_cf is not None
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
    assert not hasattr(settings.kerma_meter_correction, "mode")
    assert "mode" not in settings.kerma_meter_correction.to_dict()


def test_kerma_settings_validation_and_to_dict(tmp_path: Path):
    """Settings reject bad mode/default_factor and serialize without in_memory_table."""
    from guiskindose.settings.kerma_meter_correction_settings import (
        KermaMeterCorrectionSettings,
    )

    with pytest.raises(ValueError, match="mode must be"):  # legacy key still validated
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
            "ask_for_missing": False,
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
    assert "mode" not in payload
    assert payload["file"] == str(cf)
    assert "in_memory_table" not in payload


def test_legacy_mode_round_trip_maps_to_ask_for_missing():
    """Legacy keys load, map onto ask_for_missing, and are not re-emitted."""
    from guiskindose.settings.kerma_meter_correction_settings import KermaMeterCorrectionSettings

    assert KermaMeterCorrectionSettings({}).ask_for_missing is True  # new default
    prompt = KermaMeterCorrectionSettings({"enable": True, "mode": "prompt"})
    assert prompt.ask_for_missing is True
    file_mode = KermaMeterCorrectionSettings({"enable": True, "mode": " File "})
    assert file_mode.ask_for_missing is True  # legacy "file" was the old default: no-op
    assert KermaMeterCorrectionSettings({"prompt_at_calc": True}).ask_for_missing is True
    # An explicit ask_for_missing always beats the legacy keys.
    explicit = KermaMeterCorrectionSettings({"ask_for_missing": False, "mode": "prompt", "prompt_at_calc": True})
    assert explicit.ask_for_missing is False
    payload = explicit.to_dict()
    assert "mode" not in payload
    assert "prompt_at_calc" not in payload
    assert KermaMeterCorrectionSettings(payload).ask_for_missing is False


def _cf_for_single_unit(tmp_path: Path, *, file_cf: float | None, manual_cf: float | None, **km) -> list[float]:
    """Resolve per-event CF for the example RDSR (one unit, single tube)."""
    from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf

    if file_cf is not None:
        cf_file = tmp_path / "cf.csv"
        cf_file.write_text(f"equipment,tube,correction_factor\nunit-x,single,{file_cf}\n", encoding="utf-8")
        km["file"] = str(cf_file)
    settings = _settings(enable=True, explicit_label="unit-x", **km)
    if manual_cf is not None:
        settings.kerma_meter_correction.in_memory_table = {("unit-x", "single"): manual_cf}
    data_norm = _norm_from_example("siemens_axiom_artis.dcm", settings)
    return _resolve_kerma_meter_cf(data_norm, settings)


def test_precedence_manual_over_file_over_default(tmp_path: Path):
    """Manual entry beats the file row, which beats default_factor."""
    both = _cf_for_single_unit(tmp_path, file_cf=1.1, manual_cf=1.3, default_factor=0.9)
    assert both == pytest.approx([1.3] * len(both))
    file_only = _cf_for_single_unit(tmp_path, file_cf=1.1, manual_cf=None, default_factor=0.9)
    assert file_only == pytest.approx([1.1] * len(file_only))
    neither = _cf_for_single_unit(tmp_path, file_cf=None, manual_cf=None, default_factor=0.9)
    assert neither == pytest.approx([0.9] * len(neither))


def test_file_loads_even_when_legacy_prompt_mode_set(tmp_path: Path):
    """Legacy mode=prompt no longer causes the file to be ignored."""
    cf = _cf_for_single_unit(tmp_path, file_cf=1.1, manual_cf=None, mode="prompt", default_factor=0.9)
    assert cf == pytest.approx([1.1] * len(cf))


def test_file_miss_with_manual_entry_for_other_key_uses_default(tmp_path: Path):
    """A manual table lacking this pair does not hide the file row for it."""
    from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf

    cf_file = tmp_path / "cf.csv"
    cf_file.write_text("equipment,tube,correction_factor\nunit-x,single,1.1\n", encoding="utf-8")
    settings = _settings(enable=True, explicit_label="unit-x", file=str(cf_file), default_factor=0.9)
    settings.kerma_meter_correction.in_memory_table = {("other", "single"): 1.5}
    data_norm = _norm_from_example("siemens_axiom_artis.dcm", settings)
    factors = _resolve_kerma_meter_cf(data_norm, settings)
    assert factors == pytest.approx([1.1] * len(factors))


def test_engine_applies_per_exam_override_for_unresolved_events(tmp_path: Path):
    """An override keyed by the opaque exam label routes unresolved events to the file table."""
    import pandas as pd

    from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf

    cf_file = tmp_path / "cf.csv"
    cf_file.write_text("equipment,tube,correction_factor\nroom-9,single,1.4\n", encoding="utf-8")
    settings = _settings(enable=True, file=str(cf_file), default_factor=0.9)
    df = pd.DataFrame({"acquisition_plane": ["Single Plane"] * 2})
    assert _resolve_kerma_meter_cf(df, settings) == pytest.approx([0.9, 0.9])
    settings.kerma_meter_correction.unresolved_equipment_labels = {"Exam 2": "Room-9"}
    assert _resolve_kerma_meter_cf(df, settings) == pytest.approx([0.9, 0.9])  # wrong exam label
    assert _resolve_kerma_meter_cf(df, settings, "Exam 2") == pytest.approx([1.4, 1.4])
    settings.kerma_meter_correction.unresolved_equipment_labels = {"Exam 1": "Room-9"}
    assert _resolve_kerma_meter_cf(df, settings, None) == pytest.approx([1.4, 1.4])  # single exam = Exam 1


class _Capture:
    """Attach a list-collecting handler to the dose logger (caplog misses suite-wide state)."""

    def __init__(self) -> None:
        import logging

        self.messages: list[str] = []
        outer = self

        class _H(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                outer.messages.append(record.getMessage())

        self.handler = _H(level=logging.WARNING)
        self.logger = logging.getLogger("guiskindose.calculate_dose.calculate_dose")

    def __enter__(self) -> list[str]:
        self.logger.addHandler(self.handler)
        return self.messages

    def __exit__(self, *exc: object) -> None:
        self.logger.removeHandler(self.handler)


def _resolve_with_log(df, settings):
    from guiskindose.calculate_dose.calculate_dose import _resolve_kerma_meter_cf

    with _Capture() as messages:
        factors = _resolve_kerma_meter_cf(df, settings)
    return factors, [m for m in messages if "no factor" in m]


def test_missing_pairs_warning_logs_count_not_labels(tmp_path: Path):
    """One warning reports how many pairs lack a factor, without equipment labels."""
    import pandas as pd

    cf_file = tmp_path / "cf.csv"
    cf_file.write_text("equipment,tube,correction_factor\nsecret-room,A,1.1\n", encoding="utf-8")
    settings = _settings(enable=True, file=str(cf_file), default_factor=0.9)
    df = pd.DataFrame({"station_name": ["Secret-Room", "Secret-Room"], "acquisition_plane": ["Plane A", "Plane B"]})
    factors, messages = _resolve_with_log(df, settings)
    assert factors == pytest.approx([1.1, 0.9])
    assert len(messages) == 1
    assert "1 detected" in messages[0]
    assert "secret" not in messages[0].lower()


def test_no_missing_pairs_warning_when_table_covers_everything(tmp_path: Path):
    import pandas as pd

    cf_file = tmp_path / "cf.csv"
    cf_file.write_text("equipment,tube,correction_factor\nroom-1,A,1.1\n", encoding="utf-8")
    settings = _settings(enable=True, file=str(cf_file))
    df = pd.DataFrame({"station_name": ["Room-1"], "acquisition_plane": ["Plane A"]})
    _, messages = _resolve_with_log(df, settings)
    assert messages == []
