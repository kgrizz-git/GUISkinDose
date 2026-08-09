"""Unit tests that human/math phantoms load with head at Z≈0 (no +Z skin cells)."""

from __future__ import annotations

from pathlib import Path

from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS

import mypyskindose.constants as c
from mypyskindose.phantom_class import Phantom
from mypyskindose.settings import PyskindoseSettings

phantom_path = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "phantom_data"

param = PyskindoseSettings(DEVELOPMENT_PARAMETERS)


def test_mathematical_phantom_positioning_in_z_direction():
    # the patient phantom origin is located at the top of its head. Therefore, all
    # points on the phantom should have negative z value when loaded.

    # expect 0 skin cell have positiv z-directions, for all mathematical phantoms
    expected = [0, 0]

    actual = []

    for phantom_model in [c.PHANTOM_MODEL_PLANE, c.PHANTOM_MODEL_CYLINDER]:

        patient_phantom = Phantom(
            phantom_model=phantom_model,
            phantom_dim=param.phantom.dimension,
            human_mesh=c.PHANTOM_MESH_ADULT_MALE,
        )

        actual.append(sum(patient_phantom.r[:, 2] > 0))

    assert actual == expected


def test_stl_phantom_positioning_in_z_direction():
    # Full clinical STLs are anchored with the head at max Z ≈ 0. Reduced preview
    # companions (`*_reduced_*`) are not dose meshes and may have tiny +Z verts after
    # decimation — exclude them (same rule as mesh discovery).
    full_stems = sorted(
        p.stem for p in phantom_path.glob("*.stl") if "_reduced_" not in p.stem
    )
    assert full_stems, "expected shipped full human STLs under phantom_data/"

    actual = []
    for stem in full_stems:
        test_phantom = Phantom(
            phantom_model=c.PHANTOM_MODEL_HUMAN,
            phantom_dim=param.phantom.dimension,
            human_mesh=stem,
        )
        actual.append(int(sum(test_phantom.r[:, 2] > 0)))

    assert actual == [0] * len(full_stems)
