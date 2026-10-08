"""Unit tests for tabular import coordinate options (core; no GUI imports)."""

from pathlib import Path

import pandas as pd
import pytest

from guiskindose.input_adapters.import_options import (
    IMPORT_OPTIONS_NON_TABULAR_MESSAGE,
    TabularImportOptions,
    apply_tabular_import_coordinate_options,
    reject_import_options_for_non_tabular,
)
from guiskindose.input_adapters.registry import read_and_normalize_input
from guiskindose.main import _read_input_for_analysis, analyze_input_file, preview_input_file
from guiskindose.privacy import UserFacingInputError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabular_inputs"
GENERIC_RDSR_FIXTURE = FIXTURES / "generic_rdsr_events.csv"
NORMALIZED_FIXTURE = FIXTURES / "normalized_events.csv"
MULTISTUDY_FIXTURE = FIXTURES / "normalized_events_multistudy.csv"


def _default_settings():
    from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS

    from guiskindose.settings import PyskindoseSettings

    return PyskindoseSettings(DEVELOPMENT_PARAMETERS)


def _coord_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ("Tx", "Tz", "Ap1", "Ap2") if c in df.columns]
    return df[cols]


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Tx": [1.0, 2.0],
            "Tz": [3.0, 4.0],
            "Ap1": [10.0, 20.0],
            "Ap2": [-5.0, -6.0],
        }
    )


def test_any_set_defaults_false():
    opts = TabularImportOptions()
    assert opts.any_set() is False


def test_swap_lat_lon_alone_non_normalized():
    df = _sample_df()
    opts = TabularImportOptions(swap_lat_lon=True)
    out = apply_tabular_import_coordinate_options(df, "dosetrack", opts)
    assert list(out["Tx"]) == list(df["Tz"])
    assert list(out["Tz"]) == list(df["Tx"])
    assert list(out["Ap1"]) == list(df["Ap1"])
    assert list(out["Ap2"]) == list(df["Ap2"])


def test_flip_ap1_alone():
    df = _sample_df()
    opts = TabularImportOptions(flip_ap1=True)
    out = apply_tabular_import_coordinate_options(df, "radimetrics", opts)
    assert list(out["Ap1"]) == [-10.0, -20.0]
    assert list(out["Tx"]) == list(df["Tx"])
    assert list(out["Tz"]) == list(df["Tz"])


def test_flip_ap2_alone():
    df = _sample_df()
    opts = TabularImportOptions(flip_ap2=True)
    out = apply_tabular_import_coordinate_options(df, "generic_rdsr_like", opts)
    assert list(out["Ap2"]) == [5.0, 6.0]


def test_all_three_flags_combined_non_normalized():
    df = _sample_df()
    opts = TabularImportOptions(swap_lat_lon=True, flip_ap1=True, flip_ap2=True)
    out = apply_tabular_import_coordinate_options(df, "dosetrack", opts)
    assert list(out["Tx"]) == list(df["Tz"])
    assert list(out["Tz"]) == list(df["Tx"])
    assert list(out["Ap1"]) == [-10.0, -20.0]
    assert list(out["Ap2"]) == [5.0, 6.0]


def test_normalized_schema_swap_no_op_angle_flips_apply():
    df = _sample_df()
    opts = TabularImportOptions(swap_lat_lon=True, flip_ap1=True, flip_ap2=True)
    out = apply_tabular_import_coordinate_options(df, "normalized", opts)
    assert list(out["Tx"]) == list(df["Tx"])
    assert list(out["Tz"]) == list(df["Tz"])
    assert list(out["Ap1"]) == [-10.0, -20.0]
    assert list(out["Ap2"]) == [5.0, 6.0]


def test_all_false_options_numeric_identity():
    df = _sample_df()
    opts = TabularImportOptions()
    out = apply_tabular_import_coordinate_options(df, "dosetrack", opts)
    pd.testing.assert_frame_equal(out, df)


def test_none_options_numeric_identity():
    df = _sample_df()
    out = apply_tabular_import_coordinate_options(df, "dosetrack", None)
    pd.testing.assert_frame_equal(out, df)


def test_missing_ap_columns_skipped():
    df = pd.DataFrame({"Tx": [1.0], "Tz": [2.0]})
    opts = TabularImportOptions(flip_ap1=True, flip_ap2=True)
    out = apply_tabular_import_coordinate_options(df, "dosetrack", opts)
    pd.testing.assert_frame_equal(out, df[["Tx", "Tz"]], check_dtype=False)
    assert list(out.columns) == ["Tx", "Tz"]


def test_input_dataframe_not_mutated():
    df = _sample_df()
    original_tx = df["Tx"].tolist()
    original_tz = df["Tz"].tolist()
    original_ap1 = df["Ap1"].tolist()
    opts = TabularImportOptions(swap_lat_lon=True, flip_ap1=True, flip_ap2=True)
    apply_tabular_import_coordinate_options(df, "dosetrack", opts)
    assert df["Tx"].tolist() == original_tx
    assert df["Tz"].tolist() == original_tz
    assert df["Ap1"].tolist() == original_ap1


def test_import_options_module_has_no_gui_dependency():
    import ast
    from pathlib import Path

    import guiskindose.input_adapters.import_options as mod

    source_path = mod.__file__
    assert source_path is not None
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    gui_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            gui_imports.extend(alias.name for alias in node.names if "guiskindose.gui" in alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "guiskindose.gui" or node.module.startswith("guiskindose.gui."))
        ):
            gui_imports.append(node.module)
    assert gui_imports == []


def test_read_and_normalize_generic_rdsr_swap_lat_lon():
    settings = _default_settings()
    base = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
    )
    swapped = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
        import_options=TabularImportOptions(swap_lat_lon=True),
    )
    base_coords = _coord_columns(base.normalized_data)
    out_coords = _coord_columns(swapped.normalized_data)
    assert list(out_coords["Tx"]) == list(base_coords["Tz"])
    assert list(out_coords["Tz"]) == list(base_coords["Tx"])
    assert list(out_coords["Ap1"]) == list(base_coords["Ap1"])
    assert list(out_coords["Ap2"]) == list(base_coords["Ap2"])


def test_read_and_normalize_generic_rdsr_flip_angles():
    settings = _default_settings()
    base = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
    )
    flipped = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
        import_options=TabularImportOptions(flip_ap1=True, flip_ap2=True),
    )
    base_coords = _coord_columns(base.normalized_data)
    out_coords = _coord_columns(flipped.normalized_data)
    assert list(out_coords["Tx"]) == list(base_coords["Tx"])
    assert list(out_coords["Tz"]) == list(base_coords["Tz"])
    assert list(out_coords["Ap1"]) == [-v for v in base_coords["Ap1"]]
    assert list(out_coords["Ap2"]) == [-v for v in base_coords["Ap2"]]


def test_read_and_normalize_normalized_swap_no_op_angles_flip():
    base = read_and_normalize_input(NORMALIZED_FIXTURE)
    transformed = read_and_normalize_input(
        NORMALIZED_FIXTURE,
        import_options=TabularImportOptions(swap_lat_lon=True, flip_ap1=True, flip_ap2=True),
    )
    base_coords = _coord_columns(base.normalized_data)
    out_coords = _coord_columns(transformed.normalized_data)
    assert list(out_coords["Tx"]) == list(base_coords["Tx"])
    assert list(out_coords["Tz"]) == list(base_coords["Tz"])
    assert list(out_coords["Ap1"]) == [-v for v in base_coords["Ap1"]]
    assert list(out_coords["Ap2"]) == [-v for v in base_coords["Ap2"]]


def test_read_and_normalize_multistudy_applies_options_to_each_exam():
    base_list = read_and_normalize_input(MULTISTUDY_FIXTURE)
    flipped_list = read_and_normalize_input(
        MULTISTUDY_FIXTURE,
        import_options=TabularImportOptions(flip_ap1=True),
    )
    assert isinstance(base_list, list)
    assert isinstance(flipped_list, list)
    assert len(base_list) == len(flipped_list) == 2
    for base_item, flipped_item in zip(base_list, flipped_list, strict=True):
        base_coords = _coord_columns(base_item.normalized_data)
        out_coords = _coord_columns(flipped_item.normalized_data)
        assert list(out_coords["Ap1"]) == [-v for v in base_coords["Ap1"]]


def test_read_and_normalize_none_and_all_false_match_omitted():
    settings = _default_settings()
    omitted = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
    )
    explicit_none = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
        import_options=None,
    )
    all_false = read_and_normalize_input(
        GENERIC_RDSR_FIXTURE,
        input_schema="generic_rdsr_like",
        settings=settings,
        import_options=TabularImportOptions(),
    )
    for result in (explicit_none, all_false):
        pd.testing.assert_frame_equal(
            _coord_columns(result.normalized_data),
            _coord_columns(omitted.normalized_data),
        )


@pytest.mark.parametrize("path", ["scan.dcm", "data.json"])
def test_reject_import_options_for_non_tabular_raises(path: str):
    opts = TabularImportOptions(swap_lat_lon=True)
    with pytest.raises(UserFacingInputError) as excinfo:
        reject_import_options_for_non_tabular([path], opts)
    assert excinfo.value.user_message() == IMPORT_OPTIONS_NON_TABULAR_MESSAGE
    assert path not in str(excinfo.value)


def test_reject_mixed_tabular_and_dicom_batch():
    opts = TabularImportOptions(flip_ap1=True)
    with pytest.raises(UserFacingInputError):
        reject_import_options_for_non_tabular(["events.csv", "scan.dcm"], opts)


@pytest.mark.parametrize("options", [None, TabularImportOptions()])
def test_reject_import_options_no_op_for_dicom_without_flags(options):
    reject_import_options_for_non_tabular(["scan.dcm"], options)


def test_cli_parser_coordinate_flags_set_dests():
    from guiskindose.cli_args import get_argument_parser

    args = get_argument_parser(
        ["--swap-lat-lon", "--flip-ap1", "--flip-ap2", "--file-path", "events.csv"]
    )
    assert args.swap_lat_lon is True
    assert args.flip_ap1 is True
    assert args.flip_ap2 is True


def test_cli_parser_help_mentions_post_normalization_not_skip_transforms(capsys):
    from guiskindose.cli_args import get_argument_parser

    with pytest.raises(SystemExit) as excinfo:
        get_argument_parser(["--help"])
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert "post-normalization" in help_text.lower()
    assert "swap_lateral_longitudinal" in help_text
    assert "--skip-transforms" not in help_text


def test_read_input_for_analysis_swap_lat_lon_on_fixture():
    from guiskindose.dev_data import DEVELOPMENT_PARAMETERS
    from guiskindose.settings import PyskindoseSettings

    settings = PyskindoseSettings(DEVELOPMENT_PARAMETERS)
    base = _read_input_for_analysis(
        GENERIC_RDSR_FIXTURE,
        settings,
        "generic_rdsr_like",
        0,
        import_options=None,
    )
    swapped = _read_input_for_analysis(
        GENERIC_RDSR_FIXTURE,
        settings,
        "generic_rdsr_like",
        0,
        import_options=TabularImportOptions(swap_lat_lon=True),
    )
    base_coords = _coord_columns(base.normalized_data)
    out_coords = _coord_columns(swapped.normalized_data)
    assert list(out_coords["Tx"]) == list(base_coords["Tz"])
    assert list(out_coords["Tz"]) == list(base_coords["Tx"])


def test_analyze_input_file_dcm_with_flag_raises_before_rdsr_parse(monkeypatch: pytest.MonkeyPatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("RDSR parse should not run when import flags reject non-tabular input")

    monkeypatch.setattr(
        "guiskindose.main.read_and_normalise_rdsr_data",
        fail_if_called,
    )
    with pytest.raises(UserFacingInputError):
        analyze_input_file(
            "scan.dcm",
            import_options=TabularImportOptions(swap_lat_lon=True),
        )


def test_preview_input_file_prints_coordinate_override_line(capsys):
    from guiskindose.dev_data import DEVELOPMENT_PARAMETERS
    from guiskindose.settings import PyskindoseSettings

    preview_input_file(
        NORMALIZED_FIXTURE,
        input_schema="normalized",
        settings=PyskindoseSettings(DEVELOPMENT_PARAMETERS),
        import_options=TabularImportOptions(swap_lat_lon=True, flip_ap1=True),
    )
    captured = capsys.readouterr().out
    assert "Coordinate overrides applied: swap_lat_lon, flip_ap1" in captured
    assert str(NORMALIZED_FIXTURE) not in captured
