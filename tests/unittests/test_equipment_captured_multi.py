"""Tests for captured multi-file input through the public API.

Captures flow from real raw loads (Siemens/Philips DICOM, generic CSV/TSV/XLSX);
replay goes exclusively through ``analyze_multiple_input_files`` with
``equipment_capture_contexts`` — never through internal loaders. Covers mixed
Siemens-CFA/Philips-ASD parity against the legacy session run, same-study
separate files, reverse ordering with tuple contexts, null baseline entries,
per-exam offsets, mixed tabular formats, genuine matching import options,
divergent options, offline replay, bad-late-context zero reads, malformed-late-file
zero calculation, shape/alignment/count/aggregate refusals before any I/O,
session conflicts including all-null lists, and caller purity. No tracked
binary fixtures are used.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_profiles import assemble_session
from guiskindose.equipment_profiles.capture import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CaptureError,
)
from guiskindose.equipment_profiles.constants import MAX_PROFILES
from guiskindose.input_adapters.import_options import TabularImportOptions
from guiskindose.main import analyze_input_file, analyze_multiple_input_files
from guiskindose.settings import PyskindoseSettings
from tests.unittests.test_equipment_captured_input import (
    _GENERIC_HEADER,
    _GENERIC_PHILIPS_ROW,
    _GENERIC_SIEMENS_ROW,
    _PHILIPS_DICOM,
    _SIEMENS_DICOM,
    _code,
    _dose_settings,
    _live_capture_csv,
    _live_capture_dicom,
    _live_capture_options,
    _philips_doc,
    _siemens_doc,
    _snapshot_norm,
    _write,
)


def _session() -> Any:
    return assemble_session(documents=[_siemens_doc(), _philips_doc()])


def _matches(result: Any) -> list[Any]:
    return [exam.equipment_profile_match for exam in result.exams]


def _dense_dose_map(pairs: Any, size: int) -> Any:
    """Rebuild the dense dose map from single-run (index, value) pairs."""
    dense = np.zeros(size)
    for index, value in pairs:
        dense[int(index)] = float(value)
    return dense


def _assert_same_dose(exam: Any, single: Any) -> None:
    assert exam.output.psd == single["psd"]
    assert np.array_equal(
        np.asarray(exam.output.dose_map),
        _dense_dose_map(single["dose_map"], len(exam.output.dose_map)),
    )


# ---------------------------------------------------------------------------
# Parity against the legacy session run
# ---------------------------------------------------------------------------


def test_mixed_vendor_parity() -> None:
    session = _session()
    files = [str(_SIEMENS_DICOM), str(_PHILIPS_DICOM)]
    legacy = analyze_multiple_input_files(files, settings=_dose_settings(session))
    siemens_context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    philips_context, _ = _live_capture_dicom(_PHILIPS_DICOM, session)
    actual = analyze_multiple_input_files(
        files, settings=_dose_settings(),
        equipment_capture_contexts=[siemens_context, philips_context],
    )
    assert actual.exams_attempted == 2
    assert actual.total_events == legacy.total_events
    assert actual.aggregate_psd == legacy.aggregate_psd
    assert _matches(actual) == _matches(legacy)


def test_reverse_order_tuple() -> None:
    session = _session()
    siemens_context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    philips_context, _ = _live_capture_dicom(_PHILIPS_DICOM, session)
    forward = analyze_multiple_input_files(
        [str(_SIEMENS_DICOM), str(_PHILIPS_DICOM)], settings=_dose_settings(),
        equipment_capture_contexts=[siemens_context, philips_context],
    )
    reversed_run = analyze_multiple_input_files(
        [str(_PHILIPS_DICOM), str(_SIEMENS_DICOM)], settings=_dose_settings(),
        equipment_capture_contexts=(philips_context, siemens_context),
    )
    assert reversed_run.aggregate_psd == forward.aggregate_psd
    assert reversed_run.total_events == forward.total_events
    assert _matches(reversed_run) == _matches(forward)[::-1]


def test_same_study_separate_files(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    legacy = analyze_multiple_input_files(
        files, settings=_dose_settings(session), input_schema="generic_rdsr_like"
    )
    first_context, _, _ = _live_capture_csv(first, session)
    second_context, _, _ = _live_capture_csv(second, session)
    actual = analyze_multiple_input_files(
        files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[first_context, second_context],
    )
    assert actual.exams_attempted == 2
    assert actual.aggregate_psd == legacy.aggregate_psd
    assert _matches(actual) == _matches(legacy)


def test_tabular_mixed_formats(tmp_path: Path) -> None:
    import openpyxl
    import pandas as pd

    session = assemble_session(documents=[_siemens_doc()])
    csv_path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    raw_frame = pd.read_csv(csv_path, dtype=str)
    tsv_path = tmp_path / "events.tsv"
    raw_frame.to_csv(tsv_path, sep="\t", index=False)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(list(raw_frame.columns))
    for row in raw_frame.itertuples(index=False, name=None):
        sheet.append(list(row))
    xlsx_path = tmp_path / "events.xlsx"
    workbook.save(xlsx_path)
    files = [str(csv_path), str(tsv_path), str(xlsx_path)]
    legacy = analyze_multiple_input_files(
        files, settings=_dose_settings(session), input_schema="generic_rdsr_like"
    )
    csv_context, _, _ = _live_capture_csv(csv_path, session)
    tsv_context, _, _ = _live_capture_csv(tsv_path, session)
    xlsx_context, _, _ = _live_capture_csv(xlsx_path, session)
    actual = analyze_multiple_input_files(
        files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[csv_context, tsv_context, xlsx_context],
    )
    assert actual.exams_attempted == 3
    assert actual.aggregate_psd == legacy.aggregate_psd
    assert _matches(actual) == _matches(legacy)


def test_per_exam_offsets() -> None:
    session = _session()
    files = [str(_SIEMENS_DICOM), str(_PHILIPS_DICOM)]
    offsets = [[1.0, 2.0, 3.0], [-1.0, 0.5, 0.0]]
    legacy = analyze_multiple_input_files(
        files, settings=_dose_settings(session), per_exam_offsets=offsets
    )
    siemens_context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    philips_context, _ = _live_capture_dicom(_PHILIPS_DICOM, session)
    actual = analyze_multiple_input_files(
        files, settings=_dose_settings(), per_exam_offsets=offsets,
        equipment_capture_contexts=[siemens_context, philips_context],
    )
    assert actual.aggregate_psd == legacy.aggregate_psd
    assert _matches(actual) == _matches(legacy)


# ---------------------------------------------------------------------------
# Null baseline entries
# ---------------------------------------------------------------------------


def test_null_entries_mixed_and_all_null(tmp_path: Path) -> None:
    session = _session()
    siemens_path = _write(
        tmp_path, "siemens.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n"
    )
    philips_path = _write(
        tmp_path, "philips.csv", _GENERIC_HEADER + "\n" + _GENERIC_PHILIPS_ROW + "\n"
    )
    files = [str(siemens_path), str(philips_path)]
    legacy = analyze_multiple_input_files(
        files, settings=_dose_settings(session), input_schema="generic_rdsr_like"
    )
    siemens_context, _, _ = _live_capture_csv(siemens_path, session)
    mixed = analyze_multiple_input_files(
        files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[siemens_context, None],
    )
    assert mixed.exams_attempted == 2
    assert mixed.exams[0].equipment_profile_match == legacy.exams[0].equipment_profile_match
    assert mixed.exams[1].equipment_profile_match is None
    individual_siemens: Any = analyze_input_file(
        str(siemens_path), settings=_dose_settings(), input_schema="generic_rdsr_like"
    )
    individual_philips: Any = analyze_input_file(
        str(philips_path), settings=_dose_settings(), input_schema="generic_rdsr_like"
    )
    baseline = analyze_multiple_input_files(
        files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[None, None],
    )
    _assert_same_dose(baseline.exams[0], individual_siemens)
    _assert_same_dose(baseline.exams[1], individual_philips)


def test_null_parity_reversed_orders(tmp_path: Path) -> None:
    session = _session()
    siemens_path = _write(
        tmp_path, "siemens.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n"
    )
    philips_path = _write(
        tmp_path, "philips.csv", _GENERIC_HEADER + "\n" + _GENERIC_PHILIPS_ROW + "\n"
    )
    individual_siemens: Any = analyze_input_file(
        str(siemens_path), settings=_dose_settings(), input_schema="generic_rdsr_like"
    )
    individual_philips: Any = analyze_input_file(
        str(philips_path), settings=_dose_settings(), input_schema="generic_rdsr_like"
    )
    siemens_context, _, _ = _live_capture_csv(siemens_path, session)
    philips_context, _, _ = _live_capture_csv(philips_path, session)
    reversed_files = [str(philips_path), str(siemens_path)]
    reversed_run = analyze_multiple_input_files(
        reversed_files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[philips_context, None],
    )
    _assert_same_dose(reversed_run.exams[1], individual_siemens)
    swapped = analyze_multiple_input_files(
        reversed_files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[None, siemens_context],
    )
    _assert_same_dose(swapped.exams[0], individual_philips)


# ---------------------------------------------------------------------------
# Import options
# ---------------------------------------------------------------------------


def test_matching_import_options(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    options = TabularImportOptions(swap_lat_lon=True)
    legacy = analyze_multiple_input_files(
        files, settings=_dose_settings(session), input_schema="generic_rdsr_like",
        import_options=options,
    )
    first_context, _, _ = _live_capture_options(first, session, options)
    second_context, _, _ = _live_capture_options(second, session, options)
    actual = analyze_multiple_input_files(
        files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        import_options=options, equipment_capture_contexts=[first_context, second_context],
    )
    assert actual.aggregate_psd == legacy.aggregate_psd
    assert _matches(actual) == _matches(legacy)


def test_divergent_options(tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    first_context, _, _ = _live_capture_csv(first, session)
    second_context, _, _ = _live_capture_csv(second, session)
    options = TabularImportOptions(swap_lat_lon=True)
    raised_argument_1 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_1, input_schema="generic_rdsr_like",
            import_options=options, equipment_capture_contexts=[first_context, second_context],
        )
    assert _code(excinfo) == CODE_EQUIPMENT_GEOMETRY_MISMATCH


def test_options_non_tabular_refusal() -> None:
    session = _session()
    files = [str(_SIEMENS_DICOM), str(_PHILIPS_DICOM)]
    siemens_context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    philips_context, _ = _live_capture_dicom(_PHILIPS_DICOM, session)
    options = TabularImportOptions(swap_lat_lon=True)
    raised_argument_2 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_2, import_options=options,
            equipment_capture_contexts=[siemens_context, philips_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


# ---------------------------------------------------------------------------
# Offline replay, late failures, shape/caps, conflicts, purity
# ---------------------------------------------------------------------------


def test_offline_bundles_broken(monkeypatch: Any, tmp_path: Path) -> None:
    import json

    from guiskindose.equipment_capture import capture_to_json
    from guiskindose.equipment_profiles.capture_codec import capture_from_json
    from guiskindose.settings import normalization_settings as normalization_module

    doc = _siemens_doc()
    profile_path = tmp_path / "profiles.json"
    profile_path.write_text(json.dumps(doc), encoding="utf-8")
    from guiskindose.equipment_profiles import FileSource

    session = assemble_session(files=[FileSource(profile_path)])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    legacy = analyze_multiple_input_files(
        files, settings=_dose_settings(session), input_schema="generic_rdsr_like"
    )
    first_context, _, _ = _live_capture_csv(first, session)
    second_context, _, _ = _live_capture_csv(second, session)
    parsed: list[Any] = [capture_from_json(capture_to_json(first_context)), capture_from_json(capture_to_json(second_context))]
    profile_path.unlink()

    def _raise_selection(self: Any, data_parsed: Any) -> Any:
        raise AssertionError("bundled selection consulted during replay")

    def _raise_resolve(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("live resolver consulted during replay")

    monkeypatch.setattr(
        normalization_module.NormalizationSettings, "update_used_settings", _raise_selection
    )
    monkeypatch.setattr(
        "guiskindose.equipment_resolution.resolve_exam_coordinates", _raise_resolve
    )
    actual = analyze_multiple_input_files(
        files, settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=parsed,
    )
    assert actual.aggregate_psd == legacy.aggregate_psd
    assert _matches(actual) == _matches(legacy)


def test_bad_late_context_zero_reads(monkeypatch: Any, tmp_path: Path) -> None:
    import copy as _copy
    import pathlib

    import guiskindose.helpers.read_and_normalize_rdsr_data as dicom_helper
    import guiskindose.input_adapters.registry as registry_module

    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    first_context, _, _ = _live_capture_csv(first, session)
    second_context, _, _ = _live_capture_csv(second, session)
    forged = _copy.copy(second_context)
    object.__setattr__(forged, "event_count", "bad")
    real_load = registry_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    real_read = dicom_helper.pydicom.dcmread
    dicom_reads: list[str] = []

    def _spy_read(path: Any, *args: Any, **kwargs: Any) -> Any:
        dicom_reads.append(str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(dicom_helper.pydicom, "dcmread", _spy_read)
    real_exists = pathlib.Path.exists
    exists_probes: list[str] = []

    def _spy_exists(self: Any) -> bool:
        exists_probes.append(str(self))
        return real_exists(self)

    monkeypatch.setattr(pathlib.Path, "exists", _spy_exists)
    real_glob = pathlib.Path.glob
    glob_probes: list[str] = []

    def _spy_glob(self: Any, *args: Any, **kwargs: Any) -> Any:
        glob_probes.append(str(self))
        return real_glob(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "glob", _spy_glob)
    raised_argument_3 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_3, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[first_context, forged],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []
    assert dicom_reads == []
    assert exists_probes == []
    assert glob_probes == []


def test_malformed_late_file_no_calculation(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.equipment_captured_multi as multi_module

    session = assemble_session(documents=[_siemens_doc()])
    good = _write(tmp_path, "good.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    bad = tmp_path / "bad.dcm"
    bad.write_bytes(b"not a dicom file")
    files = [str(good), str(bad)]
    good_context, _, _ = _live_capture_csv(good, session)
    dicom_context, _ = _live_capture_dicom(_SIEMENS_DICOM, session)
    calls: list[str] = []

    def _spy_analyze(*args: Any, **kwargs: Any) -> Any:
        calls.append("analyze")
        raise AssertionError("calculation must not run after a late load failure")

    monkeypatch.setattr(multi_module, "analyze_multiple_exams", _spy_analyze)
    raised_argument_4 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_4, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[good_context, dicom_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []


def test_aggregate_event_cap(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.input_adapters.registry as registry_module

    session = assemble_session(documents=[_siemens_doc()])
    # Two files of 5_500 events each exceed the 10_000 aggregate cap.
    rows = _GENERIC_SIEMENS_ROW + "\n"
    first = _write(tmp_path, "big-a.csv", _GENERIC_HEADER + "\n" + rows * 5500)
    second = _write(tmp_path, "big-b.csv", _GENERIC_HEADER + "\n" + rows * 5500)
    files = [str(first), str(second)]
    first_context, _, _ = _live_capture_csv(first, session)
    second_context, _, _ = _live_capture_csv(second, session)
    real_load = registry_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    raised_argument_5 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_5, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[first_context, second_context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []


def test_session_conflict_all_null(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.input_adapters.registry as registry_module

    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    real_load = registry_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    raised_argument_6 = _dose_settings(session)
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_6, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[None, None],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []


def test_caller_purity_and_shield(tmp_path: Path) -> None:
    from guiskindose.equipment_captured_input import shielded_settings_for_capture

    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    first_context, _, _ = _live_capture_csv(first, session)
    second_context, _, _ = _live_capture_csv(second, session)
    fresh = _dose_settings()
    before_norm = _snapshot_norm(fresh.normalization_settings)
    before_format = fresh.output_format
    before_offset = (
        fresh.phantom.patient_offset.d_lon,
        fresh.phantom.patient_offset.d_ver,
        fresh.phantom.patient_offset.d_lat,
    )
    actual = analyze_multiple_input_files(
        files, settings=fresh, input_schema="generic_rdsr_like",
        equipment_capture_contexts=[first_context, second_context],
    )
    assert actual.exams_attempted == 2
    assert fresh.output_format == before_format
    assert _snapshot_norm(fresh.normalization_settings) == before_norm
    actual_offset = (
        fresh.phantom.patient_offset.d_lon,
        fresh.phantom.patient_offset.d_ver,
        fresh.phantom.patient_offset.d_lat,
    )
    assert actual_offset == before_offset
    cloaked = shielded_settings_for_capture(fresh)
    twice = shielded_settings_for_capture(cloaked)
    assert twice is not cloaked
    assert _snapshot_norm(twice.normalization_settings) == _snapshot_norm(cloaked.normalization_settings)


def _spy_filesystem(monkeypatch: Any) -> dict[str, list[str]]:
    """Record-delegate spies for every filesystem/source entry point."""
    import pathlib

    import guiskindose.helpers.read_and_normalize_rdsr_data as dicom_helper
    import guiskindose.input_adapters.registry as registry_module

    probes: dict[str, list[str]] = {"exists": [], "glob": [], "load": [], "dcmread": []}
    real_exists = pathlib.Path.exists

    def _spy_exists(self: Any) -> bool:
        probes["exists"].append(str(self))
        return real_exists(self)

    monkeypatch.setattr(pathlib.Path, "exists", _spy_exists)
    real_glob = pathlib.Path.glob

    def _spy_glob(self: Any, *args: Any, **kwargs: Any) -> Any:
        probes["glob"].append(str(self))
        return real_glob(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "glob", _spy_glob)
    real_load = registry_module.load

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        probes["load"].append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    real_read = dicom_helper.pydicom.dcmread

    def _spy_read(path: Any, *args: Any, **kwargs: Any) -> Any:
        probes["dcmread"].append(str(path))
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(dicom_helper.pydicom, "dcmread", _spy_read)
    return probes


def test_capture_paths_explicit_only(monkeypatch: Any, tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    first = _write(tmp_path, "a.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    second = _write(tmp_path, "b.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    files = [str(first), str(second)]
    first_context, _, _ = _live_capture_csv(first, session)
    probes = _spy_filesystem(monkeypatch)
    bad_paths: list[Any] = [
        (path for path in files),
        str(first),
        {"a": str(first)},
        [None],
        [123],
        [str(first), str(tmp_path / "*.csv")],
        [str(first), str(tmp_path / "e[0].csv")],
    ]
    for bad in bad_paths:
        raised_argument_12 = _dose_settings()
        with pytest.raises(CaptureError) as excinfo:
            analyze_multiple_input_files(
                bad, settings=raised_argument_12, input_schema="generic_rdsr_like",
                equipment_capture_contexts=[None, None],
            )
        assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    bad_contexts: list[Any] = [
        [first_context],
        [first_context, None, None],
        ["nope", None],
    ]
    for bad in bad_contexts:
        raised_argument_13 = _dose_settings()
        with pytest.raises(CaptureError) as excinfo:
            analyze_multiple_input_files(
                files, settings=raised_argument_13, input_schema="generic_rdsr_like",
                equipment_capture_contexts=bad,
            )
        assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    many = [str(_write(tmp_path, f"e{index:02d}.csv", _GENERIC_HEADER + "\n")) for index in range(MAX_PROFILES + 1)]
    nulls: list[Any] = [None] * (MAX_PROFILES + 1)
    raised_argument_7 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            many, settings=raised_argument_7, input_schema="generic_rdsr_like",
            equipment_capture_contexts=nulls,
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert probes == {"exists": [], "glob": [], "load": [], "dcmread": []}
    accepted = analyze_multiple_input_files(
        (first, second), settings=_dose_settings(), input_schema="generic_rdsr_like",
        equipment_capture_contexts=[None, None],
    )
    assert accepted.exams_attempted == 2


def test_cumulative_cap_all_null(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.input_adapters.registry as registry_module

    rows = _GENERIC_SIEMENS_ROW + "\n"
    first = _write(tmp_path, "big-a.csv", _GENERIC_HEADER + "\n" + rows * 6000)
    second = _write(tmp_path, "big-b.csv", _GENERIC_HEADER + "\n" + rows * 5000)
    third = _write(tmp_path, "small.csv", _GENERIC_HEADER + "\n" + rows * 100)
    files = [str(first), str(second), str(third)]
    real_load = registry_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    raised_argument_8 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_8, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[None, None, None],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == [str(first), str(second)]


def test_cumulative_cap_mixed(monkeypatch: Any, tmp_path: Path) -> None:
    import guiskindose.input_adapters.registry as registry_module

    session = assemble_session(documents=[_siemens_doc()])
    rows = _GENERIC_SIEMENS_ROW + "\n"
    captured_path = _write(tmp_path, "big.csv", _GENERIC_HEADER + "\n" + rows * 6000)
    null_path = _write(tmp_path, "mid.csv", _GENERIC_HEADER + "\n" + rows * 5000)
    tail_path = _write(tmp_path, "tail.csv", _GENERIC_HEADER + "\n" + rows * 100)
    files = [str(captured_path), str(null_path), str(tail_path)]
    captured_context, _, _ = _live_capture_csv(captured_path, session)
    real_load = registry_module.load
    reads: list[str] = []

    def _spy_load(path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(path))
        return real_load(path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    raised_argument_9 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            files, settings=raised_argument_9, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[captured_context, None, None],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == [str(captured_path), str(null_path)]


def test_shared_child_settings_refused(monkeypatch: Any, tmp_path: Path) -> None:
    import copy as _copy

    import guiskindose.input_adapters.registry as registry_module

    class _SharedChildSettings(PyskindoseSettings):
        def __deepcopy__(self, memo: Any) -> Any:
            clone = _copy.copy(self)
            memo[id(self)] = clone
            return clone

    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    path_str = str(path)
    context, _, _ = _live_capture_csv(path, session)
    config = load_settings_example_json()
    config["mode"] = "calculate_dose"
    fresh = _SharedChildSettings(settings=config, output_format="dict")
    before = _snapshot_norm(fresh.normalization_settings)
    real_load = registry_module.load
    reads: list[str] = []

    def _spy_load(file_path: Any, *args: Any, **kwargs: Any) -> Any:
        reads.append(str(file_path))
        return real_load(file_path, *args, **kwargs)

    monkeypatch.setattr(registry_module, "load", _spy_load)
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            [path_str], settings=fresh, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert reads == []
    assert _snapshot_norm(fresh.normalization_settings) == before


def test_json_refusal_null(tmp_path: Path) -> None:
    blob = tmp_path / "exam.json"
    blob.write_text("{}", encoding="utf-8")
    nulls: list[Any] = [None]
    raised_argument_10 = _dose_settings()
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            [blob], settings=raised_argument_10, equipment_capture_contexts=nulls
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE


def test_plot_setup_refusal_multi(monkeypatch: Any, tmp_path: Path) -> None:
    session = assemble_session(documents=[_siemens_doc()])
    path = _write(tmp_path, "events.csv", _GENERIC_HEADER + "\n" + _GENERIC_SIEMENS_ROW + "\n")
    context, _, _ = _live_capture_csv(path, session)
    config = load_settings_example_json()
    config["mode"] = "plot_setup"
    plot_settings = PyskindoseSettings(settings=config, output_format="dict")
    probes = _spy_filesystem(monkeypatch)
    raised_argument_11 = str(path)
    with pytest.raises(CaptureError) as excinfo:
        analyze_multiple_input_files(
            [raised_argument_11], settings=plot_settings, input_schema="generic_rdsr_like",
            equipment_capture_contexts=[context],
        )
    assert _code(excinfo) == CODE_INVALID_EQUIPMENT_CAPTURE
    assert probes == {"exists": [], "glob": [], "load": [], "dcmread": []}
