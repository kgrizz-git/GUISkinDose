"""Golden regression test for ``PySkinDoseOutput`` construction-time validation.

Pre-Phase-3a baseline pinning the existing ``PySkinDoseOutput.__init__``
contract (13 non-``self`` parameters). Phase 3a converts this to an
``@dataclass`` + ``__post_init__``; the validation contract — reject
mismatched list lengths with a ``ValueError`` mentioning the offending
field banner — must be preserved. The rejection tests pin each branch.

The cases use a *real* normalized RDSR DataFrame (Siemens AXIOM Artis, 21
events) as ``data_norm`` so ``EventOutput(data_norm=...)`` succeeds and the
alignment-with-``data_norm`` checks are exercised against a realistic input.
The patient / table / pad phantom inputs are lightweight mocks because this
test only exercises the dataclass validation path; the export-side
``HumanPhantomOutput`` r_ref requirement is exercised separately by the
golden dose-calc pipeline test.
"""

from __future__ import annotations

import logging
import json
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pydicom
import pytest

from mypyskindose import get_path_to_example_rdsr_files, load_settings_example_json
from mypyskindose.format_export_data import PySkinDoseOutput
from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"


@pytest.fixture(autouse=True)
def _quiet_logs():
    logging.getLogger("mypyskindose").setLevel(logging.WARNING)
    yield


@pytest.fixture
def settings() -> PyskindoseSettings:
    return PyskindoseSettings(settings=load_settings_example_json())


def _mock_phantom(phantom_model: str = "cylinder") -> MagicMock:
    """A minimal mock Phantom exposing the attributes touched by PySkinDoseOutput."""
    p = MagicMock(spec=["r", "ijk", "table_length", "phantom_model", "human_model", "r_ref"])
    p.phantom_model = phantom_model
    p.human_model = None
    p.r = np.zeros((4, 3), dtype=float)
    p.ijk = np.zeros((2, 3), dtype=int)
    p.table_length = 100.0
    p.r_ref = np.zeros((4, 3), dtype=float)
    return p


@pytest.fixture
def trio() -> tuple[MagicMock, MagicMock, MagicMock]:
    return _mock_phantom("cylinder"), _mock_phantom("table"), _mock_phantom("pad")


@pytest.fixture
def data_norm() -> pd.DataFrame:
    """Real normalized Siemens AXIOM Artis DataFrame (21 events, rotation matrices appended)."""
    s = PyskindoseSettings(settings=load_settings_example_json())
    parsed = rdsr_parser(pydicom.dcmread(str(_RDSR)), silence_pydicom_warnings=True)
    norm = rdsr_normalizer(parsed, settings=s)
    return calculate_rotation_matrices(norm)


def _aligned_kwargs(data_norm: pd.DataFrame) -> dict:
    """A complete, aligned kwargs dict for PySkinDoseOutput sized to data_norm."""
    n_events = len(data_norm)
    return {
        "dose_map": np.zeros(100, dtype=float),
        "hits": [[] for _ in range(n_events)],
        "backscatter_correction": [[] for _ in range(n_events)],
        "inverse_square_law_correction": [[] for _ in range(n_events)],
        "medium_correction": [0.0] * n_events,
        "table_correction": [0.0] * n_events,
        "data_norm": data_norm,
    }


def _build(patient, table, pad, settings, data_norm, **overrides) -> PySkinDoseOutput:
    kw = _aligned_kwargs(data_norm)
    kw["patient"] = patient
    kw["table"] = table
    kw["pad"] = pad
    kw["settings"] = settings
    kw.update(overrides)
    return PySkinDoseOutput(**kw)


def test_aligned_real_inputs_construct_without_error(settings, trio, data_norm) -> None:
    """Sanity: a fully aligned real RDSR input set must construct successfully."""
    patient, table, pad = trio
    out = _build(patient, table, pad, settings, data_norm)
    assert isinstance(out, PySkinDoseOutput)
    assert out.air_kerma == pytest.approx(1.35)


def test_output_uses_only_canonical_lowercase_object_fields(settings, trio, data_norm) -> None:
    """The object API must not retain case-colliding legacy aliases."""
    patient, table, pad = trio
    out = _build(patient, table, pad, settings, data_norm)

    field_names = tuple(PySkinDoseOutput.__dataclass_fields__)
    assert len({name.casefold() for name in field_names}) == len(field_names)
    for legacy_name in (
        "PSD",
        "AirKerma",
        "Events",
        "Patient",
        "Table",
        "Pad",
        "DoseMap",
        "Hits",
        "BackscatterCorrection",
        "InverseSquareLawCorrection",
        "MediumCorrection",
        "TableCorrection",
    ):
        assert not hasattr(out, legacy_name)


def test_serialized_export_shape_remains_stable(settings, trio, data_norm) -> None:
    """The lowercase object migration must not alter dict/JSON schema semantics."""
    patient, table, pad = trio
    exported = _build(patient, table, pad, settings, data_norm).to_dict()

    assert set(exported) == {
        "schema_version",
        "psd",
        "air_kerma",
        "air_kerma_corrected",
        "patient",
        "table",
        "pad",
        "dose_map",
        "corrections",
        "events",
    }
    assert set(exported["corrections"]) == {
        "correction_value_index",
        "backscatter",
        "medium",
        "table",
        "inverse_square_law",
        "kerma",
        "kerma_corrected",
        "kerma_meter",
    }
    assert json.loads(_build(patient, table, pad, settings, data_norm).to_json()) == exported


def test_rejects_hits_length_mismatch(settings, trio, data_norm) -> None:
    """Hits list length != data_norm length must raise ValueError mentioning 'Hits'."""
    patient, table, pad = trio
    with pytest.raises(ValueError, match="Hits"):
        _build(patient, table, pad, settings, data_norm,
               hits=[[] for _ in range(len(data_norm) + 1)])


def test_rejects_backscatter_length_mismatch(settings, trio, data_norm) -> None:
    patient, table, pad = trio
    with pytest.raises(ValueError, match="Backscatter"):
        _build(patient, table, pad, settings, data_norm,
               backscatter_correction=[[] for _ in range(len(data_norm) - 1)])


def test_rejects_inverse_square_length_mismatch(settings, trio, data_norm) -> None:
    patient, table, pad = trio
    with pytest.raises(ValueError, match="Inverse square"):
        _build(patient, table, pad, settings, data_norm,
               inverse_square_law_correction=[[] for _ in range(len(data_norm) - 1)])


def test_rejects_medium_correction_length_mismatch(settings, trio, data_norm) -> None:
    patient, table, pad = trio
    with pytest.raises(ValueError, match="Medium correction"):
        _build(patient, table, pad, settings, data_norm,
               medium_correction=[0.0] * (len(data_norm) - 1))


def test_rejects_table_correction_length_mismatch(settings, trio, data_norm) -> None:
    patient, table, pad = trio
    with pytest.raises(ValueError, match="Table correction"):
        _build(patient, table, pad, settings, data_norm,
               table_correction=[0.0] * (len(data_norm) - 1))


def test_rejects_partial_kerma_args(settings, trio, data_norm) -> None:
    """Providing kerma_meter_correction but not kerma_corrected (or vice versa) must raise."""
    patient, table, pad = trio
    with pytest.raises(ValueError, match="Kerma correction"):
        _build(patient, table, pad, settings, data_norm,
               kerma_meter_correction=[1.0] * len(data_norm))


def test_rejects_kerma_meter_length_mismatch_when_provided(settings, trio, data_norm) -> None:
    patient, table, pad = trio
    n = len(data_norm)
    with pytest.raises(ValueError, match="Kerma-meter correction"):
        _build(patient, table, pad, settings, data_norm,
               kerma_meter_correction=[1.0] * (n - 1),
               kerma_corrected=[0.1] * (n - 1))


def test_accepts_aligned_kerma_args(settings, trio, data_norm) -> None:
    """Both kerma args provided at aligned lengths must construct successfully."""
    patient, table, pad = trio
    n = len(data_norm)
    out = _build(patient, table, pad, settings, data_norm,
                 kerma_meter_correction=[1.0] * n,
                 kerma_corrected=[0.1] * n)
    assert out.kerma_meter_correction == [1.0] * n
    assert out.kerma_corrected == [0.1] * n
    assert out.air_kerma_corrected == pytest.approx(0.1 * n)


def test_missing_kerma_defaults_to_unmetered(settings, trio, data_norm) -> None:
    """Omitting both kerma args must construct with AirKerma == AirKermaCorrected."""
    patient, table, pad = trio
    out = _build(patient, table, pad, settings, data_norm)
    assert out.kerma_meter_correction == [1.0] * len(data_norm)
    assert out.air_kerma_corrected == pytest.approx(out.air_kerma)


def test_pyskindose_output_lightweight_repr() -> None:
    from mypyskindose.format_export_data import PySkinDoseOutput

    # Bypass __init__ and __post_init__ validations since fields have init=False
    out = object.__new__(PySkinDoseOutput)
    out.psd = 1.2345
    out.air_kerma = 4.5678
    out.air_kerma_corrected = 4.0
    out.pad_thickness = 2.0
    out.patient_offsets = {"long": 10.0, "vert": 5.0, "lat": -2.0}

    repr_str = repr(out)
    assert "psd=1.2345" in repr_str
    assert "air_kerma=4.5678" in repr_str
    assert "data_norm" not in repr_str
    assert "dose_map" not in repr_str


def test_pyskindose_output_repr_tolerates_uninitialized_derived_fields() -> None:
    """An exception formatter must not mask construction validation failures."""
    out = object.__new__(PySkinDoseOutput)

    assert repr(out) == (
        "PySkinDoseOutput(psd=<unavailable>, air_kerma=<unavailable>, "
        "air_kerma_corrected=<unavailable>, pad_thickness=<unavailable>, "
        "patient_offsets='<unavailable>')"
    )
