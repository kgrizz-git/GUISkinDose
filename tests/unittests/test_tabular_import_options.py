"""Unit tests for tabular import coordinate options (core; no GUI imports)."""

import pandas as pd

from guiskindose.input_adapters.import_options import (
    TabularImportOptions,
    apply_tabular_import_coordinate_options,
)


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
