"""Tests for per-event DAP / fluoro-time total capture and reporting.

Covers the input-adapter capture helper (unit detection + flagging), the
export-metric sums, and the duration formatter used by the report and GUI.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mypyskindose.export._format import fmt_duration
from mypyskindose.export.metrics import total_dap_gycm2, total_fluoro_time_s
from mypyskindose.input_adapters.base import AdapterContext, attach_procedure_dose_totals


def _ctx() -> AdapterContext:
    return AdapterContext(column_map={}, raw_headers=[], settings=None, warnings=[])


# ── capture: DAP ──────────────────────────────────────────────────────────────


class TestAttachDap:
    def test_gycm2_header_converts_and_records_units(self):
        df = pd.DataFrame({"DAP (Total) Gy-cm2": ["4.22", "0.02", "0.63"]})
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        # Gy·cm² → Gy·m² is ÷1e4; summing back gives the original Gy·cm² total.
        assert total_dap_gycm2(df) == 4.87
        assert "DoseAreaProduct_Gym2" in ctx.unit_conversions
        assert not ctx.warnings  # confident → no warning

    def test_prefers_total_over_fluoro_dap(self):
        df = pd.DataFrame(
            {
                "Fluoro DAP (Total) Gy-cm2": ["1.0", "1.0"],
                "DAP (Total) Gy-cm2": ["4.0", "6.0"],
            }
        )
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        assert total_dap_gycm2(df) == 10.0  # from the both-plane DAP, not fluoro-only

    def test_unknown_units_flagged(self):
        df = pd.DataFrame({"DAP (Total)": ["4.0", "6.0"]})  # no unit token
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        assert total_dap_gycm2(df) == 10.0  # assumed Gy·cm²
        assert any("units could not be confirmed" in w for w in ctx.warnings)

    def test_gym2_header_not_rescaled(self):
        df = pd.DataFrame({"DAP (Total) Gy·m2": ["0.001", "0.001"]})
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        # 0.002 Gy·m² == 20 Gy·cm²
        assert total_dap_gycm2(df) == 20.0

    def test_existing_dap_column_untouched(self):
        df = pd.DataFrame({"DoseAreaProduct_Gym2": [0.005], "DAP (Total) Gy-cm2": ["999"]})
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        assert total_dap_gycm2(df) == 50.0  # from the pre-existing 0.005 Gy·m²


# ── capture: fluoro time ──────────────────────────────────────────────────────


class TestAttachFluoroTime:
    def test_ms_header_converts_and_skips_nan(self):
        df = pd.DataFrame({"Fluoro time (Total) ms": ["1000", None, "2000"]})
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        # 3000 ms → 3.0 s; the NaN (acquisition) event is skipped.
        assert total_fluoro_time_s(df) == 3.0
        assert not ctx.warnings

    def test_missing_column_gives_none(self):
        df = pd.DataFrame({"kVp kV": ["70"]})
        ctx = _ctx()
        attach_procedure_dose_totals(df, ctx)
        assert total_fluoro_time_s(df) is None


# ── metrics on empty / missing frames ─────────────────────────────────────────


def test_metrics_none_when_column_absent():
    df = pd.DataFrame({"kVp": [70.0]})
    assert total_dap_gycm2(df) is None
    assert total_fluoro_time_s(df) is None


def test_metrics_none_when_all_nan():
    df = pd.DataFrame({"fluoro_time_s": [np.nan, np.nan]})
    assert total_fluoro_time_s(df) is None


# ── formatter ─────────────────────────────────────────────────────────────────


class TestFmtDuration:
    def test_none(self):
        assert fmt_duration(None) == "N/A"

    def test_under_a_minute(self):
        assert fmt_duration(42.0) == "42.0 s"

    def test_over_a_minute_shows_min_sec_and_raw(self):
        assert fmt_duration(330.8) == "5 min 30.8 s (330.8 s)"

    def test_exact_minute(self):
        assert fmt_duration(120.0) == "2 min 0.0 s (120.0 s)"
