from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.corrections import calculate_k_isq
from guiskindose.geom_calc import position_patient_phantom_on_table
from guiskindose.phantom_class import Phantom
from guiskindose.plotting.create_geometry_plot import create_geometry_plot
from guiskindose.settings import PyskindoseSettings


def _human_phantom(*, human_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> Phantom:
    settings = PyskindoseSettings(settings=load_settings_example_json())
    return Phantom(
        phantom_model=c.PHANTOM_MODEL_HUMAN,
        phantom_dim=settings.phantom.dimension,
        human_mesh="hudfrid",
        human_scale=human_scale,
    )


def test_human_scale_one_preserves_vertices_and_normals_direction():
    unscaled = _human_phantom()
    default_scaled = _human_phantom(human_scale=(1.0, 1.0, 1.0))

    np.testing.assert_allclose(default_scaled.r, unscaled.r)
    assert len(default_scaled.n) == len(default_scaled.r)

    dot = np.einsum("ij,ij->i", default_scaled.n, unscaled.n)
    assert np.all(dot > 0)


def test_human_scale_lat_doubles_lateral_extent_around_midpoint():
    unscaled = _human_phantom()
    scaled = _human_phantom(human_scale=(2.0, 1.0, 1.0))

    unscaled_mid = (unscaled.r[:, 0].min() + unscaled.r[:, 0].max()) / 2.0
    scaled_mid = (scaled.r[:, 0].min() + scaled.r[:, 0].max()) / 2.0
    unscaled_extent = unscaled.r[:, 0].max() - unscaled.r[:, 0].min()
    scaled_extent = scaled.r[:, 0].max() - scaled.r[:, 0].min()

    assert scaled_mid == pytest.approx(unscaled_mid)
    assert scaled_extent == pytest.approx(2.0 * unscaled_extent)


def test_human_scale_lon_preserves_head_origin_and_no_positive_z():
    unscaled = _human_phantom()
    scaled = _human_phantom(human_scale=(1.0, 1.0, 2.0))

    unscaled_extent = unscaled.r[:, 2].max() - unscaled.r[:, 2].min()
    scaled_extent = scaled.r[:, 2].max() - scaled.r[:, 2].min()

    assert scaled.r[:, 2].max() == pytest.approx(unscaled.r[:, 2].max())
    assert sum(scaled.r[:, 2] > 0) == 0
    assert scaled_extent == pytest.approx(2.0 * unscaled_extent)


def test_human_scale_ap_preserves_table_anchor_and_updates_extent():
    unscaled = _human_phantom()
    scaled = _human_phantom(human_scale=(1.0, 2.0, 1.0))

    unscaled_extent = unscaled.r[:, 1].max() - unscaled.r[:, 1].min()
    scaled_extent = scaled.r[:, 1].max() - scaled.r[:, 1].min()

    assert scaled.r[:, 1].max() == pytest.approx(unscaled.r[:, 1].max())
    assert scaled_extent == pytest.approx(2.0 * unscaled_extent)


def test_non_uniform_human_scale_recomputes_unit_normals():
    scaled = _human_phantom(human_scale=(1.35, 0.8, 1.2))

    lengths = np.linalg.norm(scaled.n, axis=1)
    nonzero = lengths > 0

    assert len(scaled.n) == len(scaled.r)
    assert np.allclose(lengths[nonzero], 1.0)


def test_ap_scale_changes_inverse_square_correction_for_skin_point():
    unscaled = _human_phantom()
    scaled = _human_phantom(human_scale=(1.0, 2.0, 1.0))
    cell_index = int(np.argmin(unscaled.r[:, 1]))
    source = np.array([0.0, 100.0, 0.0])
    dref = 100.0

    unscaled_k_isq = calculate_k_isq(source=source, cells=unscaled.r[cell_index], dref=dref)
    scaled_k_isq = calculate_k_isq(source=source, cells=scaled.r[cell_index], dref=dref)

    assert scaled_k_isq != pytest.approx(unscaled_k_isq)


def test_positioning_reference_contains_scaled_geometry():
    settings = PyskindoseSettings(settings=load_settings_example_json())
    patient = _human_phantom(human_scale=(1.5, 1.0, 1.0))
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    pre_position_extent = patient.r[:, 0].max() - patient.r[:, 0].min()

    position_patient_phantom_on_table(
        patient=patient,
        table=table,
        pad=pad,
        pad_thickness=settings.phantom.dimension.pad_thickness,
        patient_offset=[
            settings.phantom.patient_offset.d_lon,
            settings.phantom.patient_offset.d_ver,
            settings.phantom.patient_offset.d_lat,
        ],
        patient_orientation=settings.phantom.patient_orientation,
    )

    ref_extent = patient.r_ref[:, 0].max() - patient.r_ref[:, 0].min()
    assert ref_extent == pytest.approx(pre_position_extent)


def test_calculate_dose_constructs_human_patient_with_scale_values():
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["phantom"]["model"] = "human"
    base["phantom"]["scale_lat"] = 1.5
    base["plot"]["notebook_mode"] = False
    settings = PyskindoseSettings(settings=base)
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    norm = pd.DataFrame({"kVp": [80.0]})
    unscaled = _human_phantom()
    expected_extent = 1.5 * (unscaled.r[:, 0].max() - unscaled.r[:, 0].min())

    def _return_output_unchanged(*_args, output, **_kwargs):
        return output

    with (
        patch("guiskindose.calculate_dose.calculate_dose.position_patient_phantom_on_table"),
        patch(
            "guiskindose.calculate_dose.calculate_dose.fetch_and_append_hvl",
            side_effect=lambda data_norm, **_kw: data_norm,
        ),
        patch("guiskindose.calculate_dose.calculate_dose.check_new_geometry", return_value=[True]),
        patch("guiskindose.calculate_dose.calculate_dose.calculate_k_bs", return_value=[MagicMock()]),
        patch("guiskindose.calculate_dose.calculate_dose.calculate_k_tab", return_value=[0.8]),
        patch(
            "guiskindose.calculate_dose.calculate_dose.calculate_irradiation_event_result",
            side_effect=_return_output_unchanged,
        ),
        patch("tqdm.tqdm", return_value=MagicMock()),
    ):
        patient, output, _ = calculate_dose(normalized_data=norm, settings=settings, table=table, pad=pad)

    assert patient is not None
    assert output is not None
    actual_extent = patient.r[:, 0].max() - patient.r[:, 0].min()
    assert actual_extent == pytest.approx(expected_extent)


def test_create_geometry_plot_constructs_human_patient_with_scale_values():
    base = load_settings_example_json()
    base["mode"] = "plot_setup"
    base["phantom"]["model"] = "human"
    base["phantom"]["scale_lat"] = 1.5
    settings = PyskindoseSettings(settings=base)
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    unscaled = _human_phantom()
    expected_extent = 1.5 * (unscaled.r[:, 0].max() - unscaled.r[:, 0].min())

    with patch("guiskindose.plotting.create_geometry_plot.plot_geometry") as plot_geometry:
        create_geometry_plot(
            normalized_data=pd.DataFrame({"kVp": [80.0]}),
            table=table,
            pad=pad,
            settings=settings,
        )

    patient = plot_geometry.call_args.kwargs["patient"]
    actual_extent = patient.r[:, 0].max() - patient.r[:, 0].min()
    assert actual_extent == pytest.approx(expected_extent)


def test_phantom_settings_default_and_example_include_human_scale():
    settings = PyskindoseSettings(settings=load_settings_example_json())

    assert settings.phantom.scale_lat == pytest.approx(1.0)
    assert settings.phantom.scale_ap == pytest.approx(1.0)
    assert settings.phantom.scale_lon == pytest.approx(1.0)

    example = load_settings_example_json()
    assert example["phantom"]["scale_lat"] == pytest.approx(1.0)
    assert example["phantom"]["scale_ap"] == pytest.approx(1.0)
    assert example["phantom"]["scale_lon"] == pytest.approx(1.0)


def test_phantom_settings_missing_scale_fields_default_to_one():
    legacy = load_settings_example_json()
    legacy["phantom"].pop("scale_lat", None)
    legacy["phantom"].pop("scale_ap", None)
    legacy["phantom"].pop("scale_lon", None)

    settings = PyskindoseSettings(settings=legacy)

    assert settings.phantom.scale_lat == pytest.approx(1.0)
    assert settings.phantom.scale_ap == pytest.approx(1.0)
    assert settings.phantom.scale_lon == pytest.approx(1.0)


def test_phantom_settings_scale_values_are_clamped_with_warning():
    base = load_settings_example_json()
    base["phantom"]["scale_lat"] = 0.1
    base["phantom"]["scale_ap"] = 2.5
    base["phantom"]["scale_lon"] = 1.25
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose.settings.phantom_settings")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        settings = PyskindoseSettings(settings=base)
    finally:
        logger.removeHandler(handler)

    assert settings.phantom.scale_lat == pytest.approx(0.5)
    assert settings.phantom.scale_ap == pytest.approx(2.0)
    assert settings.phantom.scale_lon == pytest.approx(1.25)
    assert "scale_lat=0.1 outside [0.5, 2.0]; clamping" in messages
    assert "scale_ap=2.5 outside [0.5, 2.0]; clamping" in messages
