"""Regression tests for beam entrance-cell classification."""

from types import SimpleNamespace

import numpy as np

from mypyskindose.beam_class import Beam


def _beam_for_hit_tests() -> Beam:
    beam = Beam.__new__(Beam)
    beam.r = np.array([[0.0, 0.0, 0.0]])
    beam.N = np.array([[0.0, 1.0, 0.0]])
    return beam


def test_check_hit_keeps_plane_cells_inside_the_beam() -> None:
    patient = SimpleNamespace(
        r=np.array([[0.0, -1.0, 0.0], [0.0, 1.0, 0.0]]),
        phantom_model="plane",
    )

    assert _beam_for_hit_tests().check_hit(patient) == [True, False]  # type: ignore[arg-type]


def test_check_hit_excludes_non_entrance_cells_for_3d_phantoms() -> None:
    patient = SimpleNamespace(
        r=np.array([[0.0, -1.0, 0.0], [0.0, -1.0, 1.0], [0.0, 1.0, 0.0]]),
        n=np.array([[0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [0.0, 1.0, 0.0]]),
        phantom_model="human",
    )

    assert _beam_for_hit_tests().check_hit(patient) == [True, False, False]  # type: ignore[arg-type]
