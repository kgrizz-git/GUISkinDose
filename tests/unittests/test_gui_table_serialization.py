"""Unit tests for JSON-safe GUI table serialization (``to_json_safe_records``).

The Data tab RAW view shows the parsed pre-normalization frame, which carries
pydicom natives (``DSfloat``, ``DSdecimal``, ``PersonName``) and numpy scalars.
Passing those straight to ``DataFrame.to_dict("records")`` crashes NiceGUI's
orjson socket serialization (``TypeError`` on every 2 s refresh emit), so the
GUI coerces rows at the boundary instead. These tests pin that contract with a
DSfloat-bearing frame.
"""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("nicegui")

import orjson
from pydicom.uid import UID
from pydicom.valuerep import IS, DSdecimal, DSfloat, PersonName

from guiskindose.gui.helpers import to_json_safe_records


def _dsfloat_frame() -> pd.DataFrame:
    """Mimic a RAW parsed frame: object dtype preserves pydicom natives."""
    return pd.DataFrame(
        [
            {
                "dose": DSfloat("12.5"),
                "code": IS(7),
                "name": PersonName("Doe^John"),
                "uid": UID("1.2.3"),
                "count": np.int64(5),
                "ratio": np.float64(2.5),
                "flag": np.bool_(True),
                "missing": pd.NA,
                "when": datetime.datetime(2026, 1, 2, 3, 4, 5),
                "stamp": pd.Timestamp("2026-01-02 03:04:05"),
                "nat": pd.NaT,
                "nan": float("nan"),
                "pair": (1, 2),
                "tags": ["a", "b"],
                "raw": b"ab",
                "exact": DSdecimal("3.14"),
                "plain": "text",
                "whole": 9,
            }
        ],
        dtype=object,
    )


def test_dsfloat_frame_serializes() -> None:
    records = to_json_safe_records(_dsfloat_frame())
    assert len(records) == 1
    # Must not raise: this is the exact call NiceGUI makes per socket emit.
    payload = orjson.dumps(records)
    assert isinstance(payload, bytes)


def test_numbers_stay_numeric_for_sorting() -> None:
    row = to_json_safe_records(_dsfloat_frame())[0]
    assert row["dose"] == 12.5 and isinstance(row["dose"], float)
    assert row["code"] == 7 and isinstance(row["code"], int)
    assert row["count"] == 5 and isinstance(row["count"], int)
    assert row["ratio"] == 2.5 and isinstance(row["ratio"], float)
    assert row["exact"] == pytest.approx(3.14) and isinstance(row["exact"], float)
    assert row["flag"] is True
    assert row["whole"] == 9


def test_non_json_scalars_become_text_or_null() -> None:
    row = to_json_safe_records(_dsfloat_frame())[0]
    assert row["name"] == "Doe^John" and isinstance(row["name"], str)
    assert row["uid"] == "1.2.3" and isinstance(row["uid"], str)
    assert row["raw"] == "ab"
    assert row["missing"] is None
    assert row["when"] == datetime.datetime(2026, 1, 2, 3, 4, 5)
    assert row["stamp"] == "2026-01-02T03:04:05"
    assert row["nat"] is None
    assert row["plain"] == "text"


def test_nan_reaches_wire_as_null() -> None:
    row = to_json_safe_records(_dsfloat_frame())[0]
    assert row["nan"] != row["nan"]  # still NaN in the record (orjson renders null)
    assert b'"nan":null' in orjson.dumps([row])


def test_sequences_coerce_to_text() -> None:
    row = to_json_safe_records(_dsfloat_frame())[0]
    assert row["pair"] == "(1, 2)" and isinstance(row["pair"], str)
    assert row["tags"] == "['a', 'b']" and isinstance(row["tags"], str)


def test_out_of_range_int_and_signaling_nan_fallback() -> None:
    from decimal import Decimal

    df = pd.DataFrame([{"huge": 10**30, "snan": Decimal("sNaN")}], dtype=object)
    row = to_json_safe_records(df)[0]
    assert row["huge"] == str(10**30) and isinstance(row["huge"], str)
    assert row["snan"] == "sNaN"
    orjson.dumps([row])


def test_uint64_band_stays_numeric() -> None:
    df = pd.DataFrame([{"big": 2**63, "max": 2**64 - 1}], dtype=object)
    row = to_json_safe_records(df)[0]
    assert row["big"] == 2**63 and isinstance(row["big"], int)
    assert row["max"] == 2**64 - 1 and isinstance(row["max"], int)
    orjson.dumps([row])


def test_nested_dsfloat_tuple_coerces_to_text() -> None:
    """Production shape: Philips duplicate measured values arrive as tuples of
    DSfloat, which survive to_dict nested and break orjson element-wise."""
    nested = (DSfloat("0.1"), DSfloat("0.2"))
    with pytest.raises(TypeError):
        orjson.dumps([{"filter": nested}])
    df = pd.DataFrame([{"filter": nested}], dtype=object)
    row = to_json_safe_records(df)[0]
    assert row["filter"] == "('0.1', '0.2')" and isinstance(row["filter"], str)
    orjson.dumps([row])


def test_raw_to_dict_would_crash_without_coercion() -> None:
    """Guard the premise: the uncoerced frame really is unserializable."""
    with pytest.raises(TypeError):
        orjson.dumps(_dsfloat_frame().to_dict("records"))
