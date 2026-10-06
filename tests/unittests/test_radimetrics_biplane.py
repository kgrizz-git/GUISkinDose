"""Radimetrics biplane handling: per-plane A/B split and plane-identity defaults.

All fixtures are synthetic (generated in ``tmp_path``); none contain patient data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from guiskindose.input_adapters.registry import read_and_normalize_input

FIXTURES = Path(__file__).parent.parent / "fixtures" / "tabular_inputs"

_BASE_HEADERS = [
    "Manufacturer",
    "Device",
    "kVp kV",
    "Reference Point Dose (Total) mGy",
    "Source To Detector Distance (RF) [mm]",
    "Source To Isocenter Distance (RF) [mm]",
    "Table Longitudinal Position [mm]",
    "Table Lateral Position [mm]",
    "Table Height Position [mm]",
    "Primary Angle (RF) [°]",
    "Secondary Angle (RF) [°]",
    "Collimated Field Area (RF) [cm²]",
    "Xray Filter Material Codes (RF)",
    "Xray Filter Min Thicknesses",
    "Xray Filter Max Thicknesses",
]
_BASE_ROW = [
    "Siemens",
    "AXIOM-Artis",
    "77.0",
    "{total}",
    "1198.0",
    "785.0",
    "10.0",
    "5.0",
    "-150.0",
    "0.0",
    "0.0",
    "1054.4",
    "Copper or Copper compound",
    "0.6",
    "0.6",
]


def _settings():
    from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS

    from guiskindose.settings import PyskindoseSettings

    return PyskindoseSettings(DEVELOPMENT_PARAMETERS)


def _write_csv(
    tmp_path: Path,
    rows: list[dict[str, str]],
    *,
    extra_headers: list[str],
    plane_header: str | None = None,
) -> Path:
    """Write a synthetic Radimetrics CSV. Each row dict maps header → value."""
    headers = _BASE_HEADERS + extra_headers + ([plane_header] if plane_header else [])
    lines = [",".join(headers)]
    for row in rows:
        base = [c.format(total=row["total"]) for c in _BASE_ROW]
        extras = [row.get(h, "") for h in extra_headers + ([plane_header] if plane_header else [])]
        lines.append(",".join(base + extras))
    path = tmp_path / "synthetic_radimetrics.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


_A = "Reference Point Dose (A) mGy"
_B = "Reference Point Dose (B) mGy"
_PLANE_ROWS = [
    {"total": "30.0", _A: "18.0", _B: "12.0"},
    {"total": "20.0", _A: "20.0", _B: "0.0"},
    {"total": "50.0", _A: "10.0", _B: "40.0"},
]


def _tubes(norm: pd.DataFrame) -> list[str]:
    """Tube identity as the kerma-meter engine resolves it (canonical, then meaning)."""
    from guiskindose.kerma_correction import normalize_tube

    return [normalize_tube(v) for v in norm["acquisition_plane"]]


def _load(path: Path):
    return read_and_normalize_input(path, input_schema="radimetrics", settings=_settings())


class TestRadimetricsBiplaneSplit:
    def test_total_rows_replaced_by_plane_events(self, tmp_path):
        path = _write_csv(tmp_path, _PLANE_ROWS, extra_headers=[_A, _B])
        norm = _load(path).normalized_data
        # Row 2 has no B kerma, so it yields a single A event: 2 + 1 + 2 events.
        assert len(norm) == 5
        assert _tubes(norm) == ["A", "B", "A", "A", "B"]
        assert norm["acquisition_plane"].tolist() == ["Plane A", "Plane B", "Plane A", "Plane A", "Plane B"]

    def test_kerma_conserved_not_added_to_total(self, tmp_path):
        path = _write_csv(tmp_path, _PLANE_ROWS, extra_headers=[_A, _B])
        k = _load(path).normalized_data["K_IRP"].to_numpy()
        assert k == pytest.approx([18.0, 12.0, 20.0, 10.0, 40.0])
        assert k.sum() == pytest.approx(30.0 + 20.0 + 50.0)

    def test_kerma_rescaled_to_total_when_export_rounding_differs(self, tmp_path):
        rows = [{"total": "30.0", _A: "18.1", _B: "11.95"}, {"total": "10.0", _A: "5.0", _B: "5.0"}]
        path = _write_csv(tmp_path, rows, extra_headers=[_A, _B])
        k = _load(path).normalized_data["K_IRP"].to_numpy()
        assert k[0] + k[1] == pytest.approx(30.0)
        assert k[2] + k[3] == pytest.approx(10.0)

    def test_inconsistent_row_kept_as_total_with_unknown_plane(self, tmp_path):
        rows = [{"total": "30.0", _A: "18.0", _B: "12.0"}, {"total": "99.0", _A: "10.0", _B: "10.0"}]
        # Even though the file says "Single Plane", the total covers both tubes.
        for r in rows:
            r["Acquisition Plane Code (RF)"] = "Single Plane"
        path = _write_csv(tmp_path, rows, extra_headers=[_A, _B], plane_header="Acquisition Plane Code (RF)")
        norm = _load(path).normalized_data
        assert _tubes(norm) == ["A", "B", "unknown"]
        assert norm["K_IRP"].to_numpy() == pytest.approx([18.0, 12.0, 99.0])

    def test_missing_plane_column_yields_unknown_not_single(self, tmp_path):
        rows = [{"total": "30.0", _A: "18.0", _B: "12.0"}, {"total": "99.0", _A: "10.0", _B: "10.0"}]
        result = _load(_write_csv(tmp_path, rows, extra_headers=[_A, _B]))
        tubes = _tubes(result.normalized_data)
        assert "single" not in tubes
        assert tubes == ["A", "B", "unknown"]
        assert not any("defaulted to 'Single Plane'" in w for w in result.warnings)

    def test_dap_proportional_when_no_per_plane_dap(self, tmp_path):
        headers = [_A, _B, "DAP (Total) Gy-cm2"]
        rows = [{"total": "30.0", _A: "18.0", _B: "12.0", "DAP (Total) Gy-cm2": "10.0"}]
        norm = _load(_write_csv(tmp_path, rows, extra_headers=headers)).normalized_data
        dap = norm["DoseAreaProduct_Gym2"].to_numpy()
        assert dap == pytest.approx([6.0e-4, 4.0e-4])  # 10 Gy·cm² = 1e-3 Gy·m², shared 60/40
        assert dap.sum() == pytest.approx(1.0e-3)

    def test_per_plane_dap_used_and_fluoro_time_not_double_counted(self, tmp_path):
        headers = [
            _A,
            _B,
            "DAP (Total) Gy-cm2",
            "DAP (A) Gy-cm2",
            "DAP (B) Gy-cm2",
            "Fluoro Time (Total) ms",
        ]
        rows = [
            {
                "total": "30.0",
                _A: "18.0",
                _B: "12.0",
                "DAP (Total) Gy-cm2": "10.0",
                "DAP (A) Gy-cm2": "7.0",
                "DAP (B) Gy-cm2": "3.0",
                "Fluoro Time (Total) ms": "2000",
            }
        ]
        norm = _load(_write_csv(tmp_path, rows, extra_headers=headers)).normalized_data
        assert norm["DoseAreaProduct_Gym2"].to_numpy() == pytest.approx([7.0e-4, 3.0e-4])
        assert norm["fluoro_time_s"].sum() == pytest.approx(2.0)


class TestRadimetricsSinglePlaneUnchanged:
    def test_no_per_plane_columns_keeps_single_plane_default(self, tmp_path):
        rows = [{"total": "30.0"}, {"total": "20.0"}]
        result = _load(_write_csv(tmp_path, rows, extra_headers=[]))
        norm = result.normalized_data
        assert len(norm) == 2
        assert (norm["acquisition_plane"] == "Single Plane").all()
        assert any("defaulted to 'Single Plane'" in w for w in result.warnings)

    def test_per_plane_columns_with_idle_plane_b_is_not_biplane(self, tmp_path):
        rows = [{"total": "30.0", _A: "30.0", _B: "0.0"}, {"total": "20.0", _A: "20.0", _B: "0.0"}]
        norm = _load(_write_csv(tmp_path, rows, extra_headers=[_A, _B])).normalized_data
        assert len(norm) == 2
        assert (norm["acquisition_plane"] == "Single Plane").all()

    def test_bundled_current_fixture_unchanged(self):
        norm = _load(FIXTURES / "radimetrics_events.csv").normalized_data
        assert len(norm) == 5
        assert (norm["acquisition_plane"] == "Single Plane").all()
        assert _tubes(norm) == ["single"] * 5
        assert norm["K_IRP"].to_numpy() == pytest.approx([0.030, 0.020, 0.010, 0.030, 0.015])

    def test_split_returns_frame_unchanged_without_evidence(self):
        from guiskindose.input_adapters.base import AdapterContext
        from guiskindose.input_adapters.radimetrics import split_biplane_events

        df = pd.DataFrame({"DoseRP_Gy": [1.0, 2.0]})
        ctx = AdapterContext(column_map={}, raw_headers=[], settings=None, warnings=[])
        out, is_biplane = split_biplane_events(df, ctx)
        assert out is df
        assert is_biplane is False


class TestOtherAdaptersEmitBiplaneIdentity:
    """Phase 0 audit evidence: DoseTrack and generic_rdsr_like keep A/B distinct."""

    def test_dosetrack_cid_codes_give_a_and_b(self, tmp_path):
        text = (FIXTURES / "dosetrack_events.csv").read_text(encoding="utf-8").splitlines()
        # Rows 1 and 2 -> CID 10003 Plane A / Plane B codes.
        text[1] = text[1].replace(",113622,", ",113620,", 1)
        text[2] = text[2].replace(",113622,", ",113621,", 1)
        loaded = tmp_path / "dosetrack_ab.csv"
        loaded.write_text("\n".join(text) + "\n", encoding="utf-8")
        norm = read_and_normalize_input(loaded, input_schema="dosetrack", settings=_settings()).normalized_data
        assert norm["acquisition_plane_canonical"].tolist()[:3] == ["A", "B", "single"]

    def test_generic_rdsr_like_meaning_text_resolves_to_a_and_b(self, tmp_path):
        text = (FIXTURES / "generic_rdsr_events.csv").read_text(encoding="utf-8").splitlines()
        text[1] = text[1].replace(",Single Plane,", ",Plane A,", 1)
        text[2] = text[2].replace(",Single Plane,", ",Plane B,", 1)
        loaded = tmp_path / "generic_ab.csv"
        loaded.write_text("\n".join(text) + "\n", encoding="utf-8")
        norm = read_and_normalize_input(loaded, input_schema="generic_rdsr_like", settings=_settings()).normalized_data
        assert _tubes(norm)[:3] == ["A", "B", "single"]
