"""Keep dev-docs/PSD_CALCULATION_ALGORITHM.md consistent with the dose pipeline.

Machine-checked companion for the canonical PSD algorithm doc: if the pipeline
entry points, stage structure, or watched module list drift from the code, this
test fails until the doc (and the lists below) are updated.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

DOC = Path(__file__).parent.parent.parent / "dev-docs" / "PSD_CALCULATION_ALGORITHM.md"
REPO_ROOT = Path(__file__).parent.parent.parent

# Entry-point functions the doc cites. Each must remain importable.
ENTRY_POINTS: list[tuple[str, str]] = [
    ("guiskindose.analyze_data", "analyze_data"),
    ("guiskindose.analyze_data", "analyze_multiple_exams"),
    ("guiskindose.calculate_dose.calculate_dose", "calculate_dose"),
    ("guiskindose.calculate_dose.calculate_irradiation_event_result", "calculate_irradiation_event_result"),
    (
        "guiskindose.calculate_dose.perform_calculations_for_new_geometries",
        "perform_calculations_for_new_geometries",
    ),
    (
        "guiskindose.calculate_dose.add_correction_and_event_dose_to_output",
        "add_corrections_and_event_dose_to_output",
    ),
    ("guiskindose.corrections", "calculate_k_bs"),
    ("guiskindose.corrections", "calculate_k_tab"),
    ("guiskindose.corrections", "calculate_k_med"),
    ("guiskindose.corrections", "calculate_k_isq"),
    ("guiskindose.geom_calc", "check_new_geometry"),
    ("guiskindose.geom_calc", "position_patient_phantom_on_table"),
    ("guiskindose.geom_calc", "fetch_and_append_hvl"),
    ("guiskindose.geom_calc", "apply_below_floor_kvp_policy"),
]

# Stage headings the doc must keep (mirrors the user-requested 7 stages).
STAGES: list[str] = [
    "## 1. Read irradiation events",
    "## 2. Vendor / unit / coordinate transforms and offsets",
    "## 3. Correction-factor prerequisites",
    "## 4. Per-event field projection",
    "## 5. Intersections with table / pad and patient phantom",
    "## 6. Cumulative accumulation over exposures and exams",
    "## 7. Reporting",
]


@pytest.fixture(scope="module")
def doc_text() -> str:
    assert DOC.exists(), f"Missing PSD algorithm doc: {DOC}"
    return DOC.read_text(encoding="utf-8")


def test_entry_points_exist() -> None:
    """Every pipeline entry point cited by the doc must remain importable."""
    for module_name, func_name in ENTRY_POINTS:
        module = importlib.import_module(module_name)
        assert callable(getattr(module, func_name, None)), (
            f"{module_name}.{func_name} is missing; update PSD_CALCULATION_ALGORITHM.md"
        )


def test_stage_headings_present(doc_text: str) -> None:
    """The seven user-requested algorithm stages must keep their headings."""
    for heading in STAGES:
        assert heading in doc_text, f"Missing stage heading {heading!r} in {DOC.name}"


def test_entry_points_cited_in_doc(doc_text: str) -> None:
    """Every ENTRY_POINTS name must actually appear in the canonical document."""
    for _, func_name in ENTRY_POINTS:
        assert func_name in doc_text, (
            f"{func_name!r} is not cited in {DOC.name}; document it or drop it from ENTRY_POINTS"
        )


def test_stage_headings_in_execution_order(doc_text: str) -> None:
    """Stage headings must occur in execution order, not just be present."""
    positions = [doc_text.index(heading) for heading in STAGES]
    assert positions == sorted(positions), f"Stage headings out of execution order in {DOC.name}: {STAGES}"
    assert len(set(positions)) == len(STAGES)


def test_psd_is_dose_map_maximum() -> None:
    """PSD must remain the max of the (aggregate) dose map."""
    export_src = (REPO_ROOT / "src/guiskindose/format_export_data.py").read_text(encoding="utf-8")
    assert "self.psd = float(self.dose_map.max())" in export_src
    multi_src = (REPO_ROOT / "src/guiskindose/analyze_data.py").read_text(encoding="utf-8")
    assert "aggregate_psd=float(aggregate_dose_map.max())" in multi_src


def test_reporting_field_placement() -> None:
    """§7 field placement must hold: no missed-indices/warnings on the export object."""
    import dataclasses

    from guiskindose.format_export_data import PySkinDoseOutput

    output_fields = {f.name for f in dataclasses.fields(PySkinDoseOutput)}
    assert "missed_event_indices" not in output_fields
    assert "warnings" not in output_fields
    assert "kerma_corrected" in output_fields
    assert "k_tab_statuses" in output_fields
    event_src = (REPO_ROOT / "src/guiskindose/format_export_data.py").read_text(encoding="utf-8")
    assert "self.kerma = data_norm[KEY_NORMALIZATION_AIR_KERMA].tolist()" in event_src
