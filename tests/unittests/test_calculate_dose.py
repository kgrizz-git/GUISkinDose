"""Tests for ``calculate_dose`` — template shape, edge cases, and golden baseline.

The per-event slots in ``output_template`` are built by
``_build_output_template()`` with independent list/array placeholders per event.

Note on what is *not* tested here: at runtime, ``hits`` / ``k_isq`` slots
for consecutive events with identical geometry legitimately share a list
reference (``perform_calculations_for_new_geometries`` returns the same
object when ``new_geometry[ev]`` is False). So a post-run "no shared
references" assertion would be wrong for runtime output.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pydicom
import pytest

from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from mypyskindose import constants as c
from mypyskindose import get_path_to_example_rdsr_files, load_settings_example_json
from mypyskindose.calculate_dose.add_correction_and_event_dose_to_output import (
    add_corrections_and_event_dose_to_output,
)
from mypyskindose.calculate_dose.calculate_dose import (
    _build_output_template,
    calculate_dose,
)
from mypyskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)
from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from mypyskindose.phantom_class import Phantom
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
_GOLDEN_DOSE_MAP = _FIXTURES / "calculate_dose_siemens_axiom_artis_cylinder_dose_map.npy"

# Golden values captured 2026-06-16 from recursive ``calculate_dose`` on
# ``siemens_axiom_artis.dcm`` (cylinder phantom, 21 events). Any
# recursion-to-iteration refactor must produce bit-identical output.
_GOLDEN_SIEMENS_CYLINDER: dict[str, object] = {
    "events": 21,
    "dose_map_len": 9576,
    "psd_mgy": 1.3020214659058027,
    "dose_sum": 47.835152878258654,
    "kerma_first3": [0.03, 0.02, 0.01],
    "hit_counts_first3": [96, 82, 63],
    "k_med_first3": [1.038, 1.034, 1.034],
}

# Per-event slots whose final value type is mutable. "No shared references" and
# "mutation is local" checks on the *template* are only meaningful for these;
# scalar slots (``kerma``, ``k_med``, ``k_tab``) hold Python/numpy floats, which
# are immutable and safely shared (CPython caches ``0.0``).
_MUTABLE_PER_EVENT_KEYS = (
    c.OUTPUT_KEY_HITS,
    c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW,
    c.OUTPUT_KEY_CORRECTION_BACK_SCATTER,
)


@pytest.fixture(autouse=True)
def _quiet_logs():
    logging.getLogger("mypyskindose").setLevel(logging.WARNING)
    yield


# ── template builder (fast, isolated) ──────────────────────────────────


def test_output_template_placeholder_types_match_final_slot_types():
    template = _build_output_template(total_number_of_events=3, dose_map_size=50)
    n = 3

    assert len(template[c.OUTPUT_KEY_HITS]) == n
    for v in template[c.OUTPUT_KEY_HITS]:
        assert isinstance(v, list) and v == []

    assert len(template[c.OUTPUT_KEY_KERMA]) == n
    for v in template[c.OUTPUT_KEY_KERMA]:
        assert isinstance(v, float) and v == 0.0

    for key in (
        c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW,
        c.OUTPUT_KEY_CORRECTION_BACK_SCATTER,
    ):
        assert len(template[key]) == n
        for v in template[key]:
            assert isinstance(v, np.ndarray) and v.size == 0

    for key in (
        c.OUTPUT_KEY_CORRECTION_MEDIUM,
        c.OUTPUT_KEY_CORRECTION_TABLE,
    ):
        assert len(template[key]) == n
        for v in template[key]:
            assert isinstance(v, float) and v == 0.0

    assert template[c.OUTPUT_KEY_DOSE_MAP].shape == (50,)
    assert np.all(template[c.OUTPUT_KEY_DOSE_MAP] == 0.0)


def test_output_template_no_shared_references_for_mutable_slots():
    template = _build_output_template(total_number_of_events=5, dose_map_size=10)
    for key in _MUTABLE_PER_EVENT_KEYS:
        slots = template[key]
        ids = {id(s) for s in slots}
        assert len(ids) == len(slots), f"{key!r} slots share references"


def test_output_template_mutation_is_local():
    template = _build_output_template(total_number_of_events=4, dose_map_size=10)
    # list slot
    template[c.OUTPUT_KEY_HITS][0].append("probe")
    for ev in range(1, 4):
        assert template[c.OUTPUT_KEY_HITS][ev] == []

    # array slot
    template[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][0] = np.array([1.0, 2.0])
    for ev in range(1, 4):
        assert template[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev].size == 0


def test_calculate_dose_delegates_to_build_output_template():
    """``calculate_dose`` must build the per-event output via ``_build_output_template``."""
    settings = _settings()
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    norm = pd.DataFrame({"kVp": [80.0]})

    def _return_output_unchanged(*_args, output, **_kwargs):
        return output

    with (
        patch(
            "mypyskindose.calculate_dose.calculate_dose.position_patient_phantom_on_table"
        ),
        patch(
            "mypyskindose.calculate_dose.calculate_dose.fetch_and_append_hvl",
            side_effect=lambda data_norm, **_kw: data_norm,
        ),
        patch(
            "mypyskindose.calculate_dose.calculate_dose.check_new_geometry",
            return_value=[True],
        ),
        patch(
            "mypyskindose.calculate_dose.calculate_dose.calculate_k_bs",
            return_value=[MagicMock()],
        ),
        patch(
            "mypyskindose.calculate_dose.calculate_dose.calculate_k_tab",
            return_value=[0.8],
        ),
        patch(
            "mypyskindose.calculate_dose.calculate_dose._build_output_template",
            wraps=_build_output_template,
        ) as build_template,
        patch(
            "mypyskindose.calculate_dose.calculate_dose.calculate_irradiation_event_result",
            side_effect=_return_output_unchanged,
        ),
        patch("tqdm.tqdm", return_value=MagicMock()),
    ):
        patient, output = calculate_dose(
            normalized_data=norm, settings=settings, table=table, pad=pad
        )

    assert patient is not None
    assert output is not None
    build_template.assert_called_once()
    call_kwargs = build_template.call_args.kwargs
    assert call_kwargs["total_number_of_events"] == 1
    assert call_kwargs["dose_map_size"] == len(patient.r)


# ── zero-hit edge cases ────────────────────────────────────────────────


def test_add_corrections_zero_hit_writes_explicit_slots():
    """Zero-hit events must not leak template placeholders into export slots."""
    n_cells = 4
    patient = MagicMock()
    patient.r = np.zeros((n_cells, 3))
    hits = [False] * n_cells
    k_tab = [0.75]
    output = _build_output_template(total_number_of_events=1, dose_map_size=n_cells)
    dose_before = output[c.OUTPUT_KEY_DOSE_MAP].copy()

    result = add_corrections_and_event_dose_to_output(
        normalized_data=MagicMock(),
        event=0,
        hits=hits,
        table_hits=[],
        patient=patient,
        back_scatter_interpolation=[MagicMock()],
        field_area=[],
        k_tab=k_tab,
        corrections_db="unused",
        output=output,
    )

    assert result[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][0].size == 0
    assert result[c.OUTPUT_KEY_CORRECTION_MEDIUM][0] == 0.0
    assert result[c.OUTPUT_KEY_CORRECTION_TABLE][0] == 0.75
    assert np.array_equal(result[c.OUTPUT_KEY_DOSE_MAP], dose_before)


def test_perform_calculations_clears_stale_geometry_on_zero_hit():
    """New geometry with no skin hits must not reuse prior event's k_isq / field_area."""
    stale_k_isq = np.array([1.0, 2.0, 3.0])
    patient = MagicMock()
    table = MagicMock()
    pad = MagicMock()
    beam = MagicMock()
    beam.check_hit.return_value = [False, False, False]

    with patch(
        "mypyskindose.calculate_dose.perform_calculations_for_new_geometries.Beam",
        return_value=beam,
    ):
        hits, table_hits, field_area, k_isq = perform_calculations_for_new_geometries(
            normalized_data=pd.DataFrame(),
            event=0,
            new_geometry=True,
            patient=patient,
            table=table,
            pad=pad,
            hits=[True, True],
            table_hits=[True],
            field_area=[10.0, 20.0],
            k_isq=stale_k_isq,
        )

    assert hits == [False, False, False]
    assert table_hits == []
    assert field_area == []
    assert k_isq.size == 0


def test_perform_calculations_zero_hit_after_hit_event_does_not_leak_k_isq():
    """Regression: event 0 hits -> event 1 new geometry zero hits must get empty k_isq."""
    patient = MagicMock()
    patient.r = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    table = MagicMock()
    pad = MagicMock()

    hit_beam = MagicMock()
    hit_beam.check_hit.return_value = [True, False]
    hit_beam.r = np.array([[0.0, 0.0, 100.0]])

    miss_beam = MagicMock()
    miss_beam.check_hit.return_value = [False, False]

    with patch(
        "mypyskindose.calculate_dose.perform_calculations_for_new_geometries.Beam",
        side_effect=[hit_beam, miss_beam],
    ), patch(
        "mypyskindose.calculate_dose.perform_calculations_for_new_geometries.check_table_hits",
        return_value=[False],
    ), patch(
        "mypyskindose.calculate_dose.perform_calculations_for_new_geometries.scale_field_area",
        return_value=[5.0],
    ), patch(
        "mypyskindose.calculate_dose.perform_calculations_for_new_geometries.calculate_k_isq",
        return_value=np.array([0.5]),
    ):
        norm = pd.DataFrame({c.DATA_DS_IRP: [100.0]})
        hits_ev0, table_hits_ev0, field_area_ev0, k_isq_ev0 = perform_calculations_for_new_geometries(
            normalized_data=norm,
            event=0,
            new_geometry=True,
            patient=patient,
            table=table,
            pad=pad,
            hits=[],
            table_hits=[],
            field_area=[],
            k_isq=np.array([]),
        )
        _, table_hits_ev1, field_area_ev1, k_isq_ev1 = perform_calculations_for_new_geometries(
            normalized_data=norm,
            event=1,
            new_geometry=True,
            patient=patient,
            table=table,
            pad=pad,
            hits=hits_ev0,
            table_hits=table_hits_ev0,
            field_area=field_area_ev0,
            k_isq=k_isq_ev0,
        )

    assert k_isq_ev0.shape == (1,)
    assert k_isq_ev1.size == 0
    assert field_area_ev1 == []
    assert table_hits_ev1 == []


# ── end-to-end via calculate_dose (smoke + slot-type pin) ──────────────


def _settings(*, phantom_model: str = "cylinder") -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = phantom_model
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    return PyskindoseSettings(settings=base)


def _run_calculate_dose():
    settings = _settings()
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    parsed = rdsr_parser(pydicom.dcmread(str(_RDSR)), silence_pydicom_warnings=True)
    norm = rdsr_normalizer(parsed, settings=settings)
    norm = calculate_rotation_matrices(norm)
    _, output = calculate_dose(normalized_data=norm, settings=settings, table=table, pad=pad)
    assert output is not None
    return output


def test_calculate_dose_runs_and_fills_per_event_slots():
    """Smoke: every per-event slot is overwritten with a correctly-typed value."""
    output = _run_calculate_dose()
    n = len(output[c.OUTPUT_KEY_HITS])
    assert n > 0
    for ev in range(n):
        assert isinstance(output[c.OUTPUT_KEY_HITS][ev], list)
        # numpy.float64 is a subclass of Python float
        assert isinstance(output[c.OUTPUT_KEY_KERMA][ev], float)
        assert isinstance(output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev], np.ndarray)
        assert isinstance(output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][ev], np.ndarray)
        # k_med is a scalar — `calculate_k_med` returns float
        assert isinstance(output[c.OUTPUT_KEY_CORRECTION_MEDIUM][ev], float)
        assert isinstance(output[c.OUTPUT_KEY_CORRECTION_TABLE][ev], float)
    assert isinstance(output[c.OUTPUT_KEY_DOSE_MAP], np.ndarray)
    assert output[c.OUTPUT_KEY_DOSE_MAP].ndim == 1
    # non-negative dose
    assert np.all(output[c.OUTPUT_KEY_DOSE_MAP] >= 0.0)


# ── recursion-to-iteration prep (golden baseline + stress) ─────────────


def test_calculate_dose_golden_baseline_siemens_cylinder():
    """Recursive output pinned; loop refactor must stay bit-identical."""
    output = _run_calculate_dose()
    golden = _GOLDEN_SIEMENS_CYLINDER
    dose_map = output[c.OUTPUT_KEY_DOSE_MAP]

    assert len(output[c.OUTPUT_KEY_HITS]) == golden["events"]
    assert len(dose_map) == golden["dose_map_len"]
    assert float(np.max(dose_map)) == pytest.approx(golden["psd_mgy"])
    assert float(np.sum(dose_map)) == pytest.approx(golden["dose_sum"])

    for ev, expected_kerma in enumerate(golden["kerma_first3"]):
        assert output[c.OUTPUT_KEY_KERMA][ev] == pytest.approx(expected_kerma)
        assert sum(output[c.OUTPUT_KEY_HITS][ev]) == golden["hit_counts_first3"][ev]
        assert output[c.OUTPUT_KEY_CORRECTION_MEDIUM][ev] == pytest.approx(golden["k_med_first3"][ev])

    expected_dose_map = np.load(_GOLDEN_DOSE_MAP)
    np.testing.assert_array_equal(dose_map, expected_dose_map)


@pytest.mark.slow
def test_calculate_dose_handles_1100_events_without_recursion_error():
    """Stress: >1000 events must not hit Python's recursion limit after refactor."""
    n_events = 1100
    settings = _settings(phantom_model="plane")
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    norm = generate_synthetic_normalized_events(n_events)

    _, output = calculate_dose(normalized_data=norm, settings=settings, table=table, pad=pad)
    assert output is not None
    assert len(output[c.OUTPUT_KEY_HITS]) == n_events
    assert np.any(output[c.OUTPUT_KEY_DOSE_MAP] > 0.0)
