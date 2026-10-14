"""Unit tests for DICOM zero-kVp row removal before authority confirmation."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from guiskindose.gui.exam_equipment import _drop_zero_kvp_rows


def test_drop_zero_kvp_rows_noop_when_removal_disabled() -> None:
    df = pd.DataFrame({"kVp": [0, 80.0, 0]})
    settings = SimpleNamespace(remove_invalid_rows=False)
    out = _drop_zero_kvp_rows(df, settings)
    pd.testing.assert_frame_equal(out, df)


def test_drop_zero_kvp_rows_noop_when_no_zero_rows() -> None:
    df = pd.DataFrame({"kVp": [70.0, 80.0]})
    settings = SimpleNamespace(remove_invalid_rows=True)
    out = _drop_zero_kvp_rows(df, settings)
    pd.testing.assert_frame_equal(out, df)


def test_drop_zero_kvp_rows_filters_when_enabled() -> None:
    df = pd.DataFrame({"kVp": [0, 80.0, 0], "DAP": [1.0, 2.0, 3.0]})
    settings = SimpleNamespace(remove_invalid_rows=True)
    out = _drop_zero_kvp_rows(df, settings)
    assert list(out["kVp"]) == [80.0]
    assert list(out["DAP"]) == [2.0]
    assert out.index.tolist() == [0]
