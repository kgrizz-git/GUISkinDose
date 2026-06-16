"""Tests for ``calculate_dose`` — pins the ``output_template`` shape.

The per-event slots in ``output_template`` are constructed once and then
overwritten on every event, so the bug is latent: ``[[]] * N`` and
``[np.array] * N`` (the previous values) produced shared references and
the ``np.array`` *class* respectively, which would silently corrupt the
dict on any future in-place mutation or pre-assignment read.

Note on what is *not* tested here: at runtime, ``hits`` / ``k_isq`` slots
for consecutive events with identical geometry legitimately share a list
reference (``perform_calculations_for_new_geometries`` returns the same
object when ``new_geometry[ev]`` is False). So a post-run "no shared
references" assertion would be wrong; the bug is in the template, not
the runtime.
"""

from __future__ import annotations

import inspect
import logging

import numpy as np
import pydicom
import pytest

from mypyskindose import constants as c
from mypyskindose import get_path_to_example_rdsr_files, load_settings_example_json
from mypyskindose.calculate_dose.calculate_dose import (
    _build_output_template,
    calculate_dose,
)
from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from mypyskindose.phantom_class import Phantom
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"

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
        c.OUTPUT_KEY_CORRECTION_MEDIUM,
    ):
        assert len(template[key]) == n
        for v in template[key]:
            assert isinstance(v, np.ndarray) and v.size == 0

    assert len(template[c.OUTPUT_KEY_CORRECTION_TABLE]) == n
    for v in template[c.OUTPUT_KEY_CORRECTION_TABLE]:
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


def test_calculate_dose_uses_template_builder_not_inline_literal():
    """Pin the call site: ``calculate_dose`` must delegate to
    ``_build_output_template`` rather than reconstructing the
    shared-reference template inline.
    """
    source = inspect.getsource(calculate_dose)
    assert "_build_output_template" in source, (
        "calculate_dose must call _build_output_template; "
        "the inline [[]] * N / [np.array] * N literal is the bug we are fixing"
    )
    assert "[[]] *" not in source, "inline [[]] * N literal reintroduces the shared-reference bug"
    assert "[np.array] *" not in source, "inline [np.array] * N literal reintroduces the class-placeholder bug"


# ── end-to-end via calculate_dose (smoke + slot-type pin) ──────────────


def _settings() -> PyskindoseSettings:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "cylinder"
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
