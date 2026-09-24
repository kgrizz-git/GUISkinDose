from pathlib import Path

import pytest
from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS

from guiskindose import load_settings_example_json
from guiskindose.settings import PyskindoseSettings

settings = PyskindoseSettings(settings=DEVELOPMENT_PARAMETERS)


def test_that_print_parameters_function_updates_output_after_settings_change():

    print_string = settings.print_parameters(return_as_string=True)

    settings.mode = "some_other_mode"

    print_string_updated = settings.print_parameters(return_as_string=True)

    assert print_string != print_string_updated


def test_that_file_output_directory_is_set_to_a_subdirectory_to_cwd_if_not_specified():
    expected = Path.cwd() / "PlotOutputs"

    assert settings.file_result_output_path.absolute() == expected.absolute()


def test_that_file_output_directory_is_set_to_specified_directory():
    expected = Path(__file__).parent.parent

    actual = PyskindoseSettings(
        settings=DEVELOPMENT_PARAMETERS, file_result_output_path=expected
    ).file_result_output_path

    assert actual == expected


def _settings_with(**overrides) -> PyskindoseSettings:
    base = load_settings_example_json()
    base.update(overrides)
    return PyskindoseSettings(settings=base)


def test_angular_step_deg_accepts_documented_bounds():
    assert _settings_with(angular_step_deg=0.25).angular_step_deg == 0.25
    assert _settings_with(angular_step_deg=10.0).angular_step_deg == 10.0


def test_angular_step_deg_rejects_out_of_range_values():
    for value in (0.2, 10.1):
        with pytest.raises(ValueError, match="angular_step_deg"):
            _settings_with(angular_step_deg=value)


def test_angular_step_deg_rejects_boolean_values():
    # float(True) == 1.0 would silently pass the range check otherwise.
    for value in (True, False):
        with pytest.raises(ValueError, match="angular_step_deg"):
            _settings_with(angular_step_deg=value)


def test_angular_step_deg_rejects_non_numeric_values():
    # float("5") == 5.0 would silently coerce a string config value.
    for value in ("5", None):
        with pytest.raises(ValueError, match="angular_step_deg"):
            _settings_with(angular_step_deg=value)


def test_include_static_pose_defaults_true_when_absent():
    base = load_settings_example_json()
    del base["include_static_pose"]
    assert PyskindoseSettings(settings=base).include_static_pose is True


def test_include_static_pose_rejects_non_boolean():
    with pytest.raises(ValueError, match="include_static_pose"):
        _settings_with(include_static_pose="false")
