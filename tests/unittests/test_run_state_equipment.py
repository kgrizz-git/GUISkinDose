"""Boundary tests for the run-state equipment envelope (foundation, inert).

Every capture here is real: an approved-DICOM receipt through
``capture_from_receipt`` with a memory session, serialized only through the
existing core producer. These tests cover the wrapper contract only —
unspecified-vs-present decode, positional alignment, code translation, count
bounds, forgery refusal, cancellation, repr privacy, and import lightness —
never core codec behavior already covered by committed capture tests.
"""

from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path
from typing import Any, Self
from unittest import mock

import pytest

from guiskindose import load_settings_example_json
from guiskindose.equipment_capture import capture_from_receipt, envelope_to_mapping
from guiskindose.equipment_profiles import assemble_session
from guiskindose.equipment_profiles.capture import CapturedCoordinates
from guiskindose.equipment_profiles.capture_checks import (
    CODE_EQUIPMENT_GEOMETRY_MISMATCH,
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION,
    CaptureError,
)
from guiskindose.gui.run_state_equipment import (
    decode_equipment_section,
    emit_equipment_section,
)
from guiskindose.gui.run_state_errors import RunStateError
from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from guiskindose.settings import PyskindoseSettings

_DICOM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "guiskindose"
    / "example_data"
    / "RDSR"
    / "siemens_axiom_artis.dcm"
)


def _profile_doc() -> dict[str, Any]:
    """Single memory profile matching the approved Siemens fixture."""
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": "runstate-full",
                "manufacturer": "Siemens",
                "models": ["AXIOM-Artis"],
                "coordinates": {
                    "translation_offset": {"x": 5.0, "y": -3.5, "z": 0.0},
                    "translation_direction": {"x": "+", "y": "-", "z": "+"},
                    "rotation_direction": {
                        "Ap1": "-",
                        "Ap2": "+",
                        "Ap3": "+",
                        "At1": "+",
                        "At2": "-",
                        "At3": "+",
                    },
                    "swap_lateral_longitudinal": False,
                    "field_size_mode": "CFA",
                    "detector_side_length": 30.0,
                },
            }
        ],
    }


@pytest.fixture(scope="module")
def dicom_capture() -> CapturedCoordinates:
    """Real capture from the approved DICOM through the bound session."""
    session = assemble_session(documents=[_profile_doc()])
    settings = PyskindoseSettings(
        settings=load_settings_example_json(), equipment_profile_session=session
    )
    out: list[Any] = []
    frame = read_and_normalise_rdsr_data(str(_DICOM), settings, equipment_receipt_out=out)
    assert len(out) == 1
    return capture_from_receipt(receipt=out[0], frame=frame, settings=settings)


@pytest.fixture(scope="module")
def dicom_mapping(dicom_capture: CapturedCoordinates) -> dict[str, Any]:
    """Canonical producer mapping of the shared real capture."""
    envelope = envelope_to_mapping([dicom_capture])
    entry = envelope["captures"][0]
    assert isinstance(entry, dict)
    return entry


def _tampered(mapping: dict[str, Any]) -> dict[str, Any]:
    """Copy with a recipe leaf moved but the checksum left stale."""
    broken = copy.deepcopy(mapping)
    broken["effective_coordinates"]["translation_offset"]["x"] += 1.0
    return broken


def _no_diagnostic_calls(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Spy the entry probe: any call raises, so silence proves no traversal."""
    calls: list[Any] = []

    def _boom(entry: Any) -> Any:
        calls.append(entry)
        raise AssertionError("diagnostic path must not parse entries")

    monkeypatch.setattr("guiskindose.gui.run_state_equipment.capture_from_mapping", _boom)
    return calls


def _deep_dict(depth: int) -> dict[str, Any]:
    """Benign nesting past the core depth cap (budget failure, fast)."""
    node: dict[str, Any] = {}
    for _ in range(depth):
        node = {"nested": node}
    return node


class _HostileKey:
    """Mapping key whose equality must never run during diagnosis."""

    def __init__(self, bucket: int) -> None:
        self._bucket = bucket

    def __hash__(self) -> int:
        return self._bucket

    def __eq__(self, other: object) -> Any:
        raise AssertionError("hostile key equality invoked")


class _HostileText(str):
    """Exact-type gate proof: same text as a locked key, but not a plain str."""

    _bucket: int

    def __new__(cls, content: str, bucket: int) -> Self:
        self = super().__new__(cls, content)
        self._bucket = bucket
        return self

    def __hash__(self) -> int:
        return self._bucket

    def __eq__(self, other: object) -> Any:
        raise AssertionError("hostile key equality invoked")


def _free_bucket(keys: list[str]) -> int:
    """A table bucket no benign key occupies (8-slot tables never resize here)."""
    taken = {hash(key) & 7 for key in keys}
    for bucket in range(8):
        if bucket not in taken:
            return bucket
    raise AssertionError("no free bucket")


def test_error_identity_matches_legacy_import() -> None:
    """The move keeps one class: run_state re-exports run_state_errors."""
    from guiskindose.gui import run_state, run_state_errors

    assert run_state.RunStateError is run_state_errors.RunStateError


@pytest.mark.parametrize("exam_count", [0, 2])
def test_decode_absent_is_unspecified(exam_count: int) -> None:
    """Absent equipment skips restore; live state stays untouched."""
    assert decode_equipment_section(None, exam_count=exam_count) is None


def test_decode_roundtrip_single(dicom_capture: CapturedCoordinates) -> None:
    """Producer envelope decodes back to the identical authority."""
    section = envelope_to_mapping([dicom_capture])
    parsed = decode_equipment_section(section, exam_count=1)
    assert parsed is not None
    assert parsed[0] == dicom_capture


def test_decode_null_entries_stay_positional(dicom_capture: CapturedCoordinates) -> None:
    """Nulls ride through in place; no partial list is ever assembled."""
    section = envelope_to_mapping([dicom_capture, None, dicom_capture])
    parsed = decode_equipment_section(section, exam_count=3)
    assert parsed == (dicom_capture, None, dicom_capture)


def test_decode_empty_envelope_matches_zero_exams() -> None:
    """Zero exams align with an explicitly empty capture list."""
    assert decode_equipment_section(envelope_to_mapping([]), exam_count=0) == ()


@pytest.mark.parametrize("exam_count", [0, 2])
def test_decode_count_mismatch_rejects_whole_section(
    dicom_capture: CapturedCoordinates, exam_count: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One entry against a different exam count refuses before any decoding."""
    calls = _no_diagnostic_calls(monkeypatch)

    def _boom(document: Any) -> Any:
        raise AssertionError("misaligned list must not decode")

    monkeypatch.setattr("guiskindose.gui.run_state_equipment.parse_envelope", _boom)
    section = envelope_to_mapping([dicom_capture])
    with pytest.raises(RunStateError, match="does not match the exam count"):
        decode_equipment_section(section, exam_count=exam_count)
    assert calls == []


@pytest.mark.parametrize("exam_count", [True, -1, "1", 1.0, None])
def test_decode_exam_count_mistypes_fail_closed(
    dicom_capture: CapturedCoordinates, exam_count: Any
) -> None:
    """Booleans, negatives, and non-integers never align."""
    section = envelope_to_mapping([dicom_capture])
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=exam_count)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_decode_exam_count_over_cap_message(dicom_capture: CapturedCoordinates) -> None:
    """Over-64 counts surface a dedicated bound message, not a generic mismatch."""
    section = envelope_to_mapping([dicom_capture])
    with pytest.raises(RunStateError, match="Too many exams for equipment capture section"):
        decode_equipment_section(section, exam_count=65)


@pytest.mark.parametrize("section", ["{\"a\": 1}", 5, ["captures"]])
def test_decode_section_mistypes_fail_closed(section: Any) -> None:
    """Text, scalars, and lists are not envelopes; no position is named."""
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_decode_missing_captures_names_no_position(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dict without the captures list fails envelope-level, position-free."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {"schema_version": 1, "mode": "coordinates"}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "Exam" not in str(excinfo.value)
    assert calls == []


def test_decode_unknown_envelope_key_names_no_position(
    dicom_mapping: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown keys fail closed even when every entry parses on its own."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [_tampered(dicom_mapping)],
        "future": {},
    }
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "Exam" not in str(excinfo.value)
    assert calls == []


def test_decode_unsupported_schema_version(
    dicom_mapping: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A future envelope version translates to the version code, entry-blind."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {
        "schema_version": 2,
        "mode": "coordinates",
        "captures": [_tampered(dicom_mapping)],
    }
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION
    assert "Exam" not in str(excinfo.value)
    assert calls == []


def test_decode_non_integer_schema_version_is_unsupported(
    dicom_mapping: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-integer version is a version failure, never a structural one."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {
        "schema_version": "1",
        "mode": "coordinates",
        "captures": [_tampered(dicom_mapping)],
    }
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_UNSUPPORTED_EQUIPMENT_CAPTURE_VERSION
    assert "Exam" not in str(excinfo.value)
    assert calls == []


def test_decode_unknown_mode_is_invalid(
    dicom_mapping: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-coordinates mode is malformed content, not a version gap."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {
        "schema_version": 1,
        "mode": "other",
        "captures": [_tampered(dicom_mapping)],
    }
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "Exam" not in str(excinfo.value)
    assert calls == []


def test_decode_tampered_first_entry_names_exam_1(
    dicom_mapping: dict[str, Any],
) -> None:
    """A stale checksum rejects the section at its opaque position."""
    section = {"schema_version": 1, "mode": "coordinates", "captures": [_tampered(dicom_mapping)]}
    with pytest.raises(RunStateError, match=r"\(Exam 1\)"):
        decode_equipment_section(section, exam_count=1)


def test_decode_tampered_second_entry_names_exam_2(
    dicom_mapping: dict[str, Any],
) -> None:
    """Nulls are skipped while locating the failing opaque position."""
    section = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [None, _tampered(dicom_mapping)],
    }
    with pytest.raises(RunStateError, match=r"\(Exam 2\)"):
        decode_equipment_section(section, exam_count=2)


def test_decode_failure_hides_document_values(dicom_mapping: dict[str, Any]) -> None:
    """Messages and reprs never echo maker, model, profile, or hash text."""
    section = {"schema_version": 1, "mode": "coordinates", "captures": [_tampered(dicom_mapping)]}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    text = str(excinfo.value) + repr(excinfo.value)
    leaked = (
        "Siemens",
        "AXIOM-Artis",
        "runstate-full",
        dicom_mapping["geometry_hash"],
        dicom_mapping["capture_hash"],
        dicom_mapping["match"]["profile_hash"],
    )
    assert not any(marker in text for marker in leaked)


def test_decode_unknown_core_code_falls_back_closed(
    dicom_mapping: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A future core code the table does not know still refuses as invalid."""

    def _future(document: Any) -> Any:
        raise CaptureError("future core failure", "bogus-future-code")

    monkeypatch.setattr(
        "guiskindose.gui.run_state_equipment.parse_envelope", _future
    )
    section = {"schema_version": 1, "mode": "coordinates", "captures": [dicom_mapping]}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_decode_over_count_bound_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sixty-five entries exceed the per-envelope bound without traversal."""
    calls = _no_diagnostic_calls(monkeypatch)
    oversized = {"schema_version": 1, "mode": "coordinates", "captures": [None] * 65}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(oversized, exam_count=64)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert calls == []


def test_decode_massive_list_rejects_on_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """A million-entry list rejects on count; entries are never scanned."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {"schema_version": 1, "mode": "coordinates", "captures": [None] * 1_000_000}
    with pytest.raises(RunStateError, match="does not match the exam count"):
        decode_equipment_section(section, exam_count=64)
    assert calls == []


def test_decode_deep_document_skips_localization(monkeypatch: pytest.MonkeyPatch) -> None:
    """A depth-budget failure never triggers a second unbounded traversal."""
    calls = _no_diagnostic_calls(monkeypatch)
    section = {"schema_version": 1, "mode": "coordinates", "captures": [_deep_dict(64)]}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "Exam" not in str(excinfo.value)
    assert calls == []


@pytest.mark.parametrize("hostile", ["object", "subclass"])
def test_decode_hostile_keys_never_equated(
    hostile: str, dicom_mapping: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-plain-str keys fail diagnosis without their equality ever running.

    The section is otherwise a valid envelope around a tampered entry, so a
    regressed key lookup would find the captures list and misname an exam;
    the gate refuses on the hostile key first. The hostile key sits in a
    bucket no benign key occupies, keeping even container construction
    deterministic across hash seeds.
    """
    calls = _no_diagnostic_calls(monkeypatch)
    bucket = _free_bucket(["schema_version", "mode", "captures"])
    if hostile == "object":
        key: Any = _HostileKey(bucket)
    else:
        key = _HostileText("schema_version", bucket)
    section = {
        "schema_version": 1,
        "mode": "coordinates",
        "captures": [_tampered(dicom_mapping)],
        key: None,
    }
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "Exam" not in str(excinfo.value)
    assert calls == []


@pytest.mark.parametrize("escape", [KeyboardInterrupt, SystemExit])
def test_decode_cancellation_passes_through(
    monkeypatch: pytest.MonkeyPatch, escape: Any
) -> None:
    """Only CaptureError translates; cancellation escapes unchanged."""

    def _cancel(document: Any) -> Any:
        raise escape()

    monkeypatch.setattr("guiskindose.gui.run_state_equipment.parse_envelope", _cancel)
    with pytest.raises(escape):
        decode_equipment_section({"schema_version": 1}, exam_count=0)


@pytest.mark.parametrize("escape", [KeyboardInterrupt, SystemExit])
def test_emit_cancellation_passes_through(
    dicom_capture: CapturedCoordinates, monkeypatch: pytest.MonkeyPatch, escape: Any
) -> None:
    """Only CaptureError translates on emission; cancellation escapes unchanged."""

    def _cancel(captures: Any) -> Any:
        raise escape()

    monkeypatch.setattr("guiskindose.gui.run_state_equipment.envelope_to_mapping", _cancel)
    with pytest.raises(escape):
        emit_equipment_section([dicom_capture], exam_count=1)


def test_emit_roundtrip_is_canonical(dicom_capture: CapturedCoordinates) -> None:
    """Emission matches the core producer byte-for-byte in shape."""
    emitted = emit_equipment_section([dicom_capture, None], exam_count=2)
    assert emitted == envelope_to_mapping([dicom_capture, None])


def test_emit_accepts_tuples(dicom_capture: CapturedCoordinates) -> None:
    """Tuples emit exactly like lists; the envelope holds the alignment."""
    assert emit_equipment_section((dicom_capture,), exam_count=1) == envelope_to_mapping(
        (dicom_capture,)
    )


@pytest.mark.parametrize("captures", [{"captures": []}, "[capture]"])
def test_emit_non_sequences_fail_closed(captures: Any) -> None:
    """Mappings and text are not per-exam context sequences."""
    with pytest.raises(RunStateError) as excinfo:
        emit_equipment_section(captures, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_emit_length_mismatch_names_count(dicom_capture: CapturedCoordinates) -> None:
    """A short list against the exam count refuses before any hashing."""
    with pytest.raises(RunStateError, match="does not match the exam count"):
        emit_equipment_section([dicom_capture], exam_count=2)


@pytest.mark.parametrize("captures", [["not-a-context"], [{}], [(None,)]])
def test_emit_mistyped_entries_fail_closed(captures: Any) -> None:
    """Only real contexts or explicit nulls may occupy a position."""
    with pytest.raises(RunStateError) as excinfo:
        emit_equipment_section(captures, exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_emit_stale_count_forgery_refuses(dicom_capture: CapturedCoordinates) -> None:
    """A memory-forged count bypassing construction fails emission revalidation."""
    forged = copy.copy(dicom_capture)
    object.__setattr__(forged, "event_count", dicom_capture.event_count + 1)
    with pytest.raises(RunStateError) as excinfo:
        emit_equipment_section([forged], exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_emit_mutated_field_type_refuses(dicom_capture: CapturedCoordinates) -> None:
    """A memory-mutated wrong-typed field fails revalidation on emission."""
    forged = copy.copy(dicom_capture)
    object.__setattr__(forged, "profile_id", 123)
    with pytest.raises(RunStateError) as excinfo:
        emit_equipment_section([forged], exam_count=1)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_emit_over_count_bound_refuses(dicom_capture: CapturedCoordinates) -> None:
    """Sixty-five positions exceed the exam-count bound before any hashing."""
    with pytest.raises(RunStateError) as excinfo:
        emit_equipment_section([dicom_capture] * 65, exam_count=65)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE


def test_emit_geometry_mismatch_code_translates(
    dicom_capture: CapturedCoordinates, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The restore-boundary code maps to its fixed run-state message."""

    def _mismatch(captures: Any) -> Any:
        raise CaptureError("stale geometry", CODE_EQUIPMENT_GEOMETRY_MISMATCH)

    monkeypatch.setattr(
        "guiskindose.gui.run_state_equipment.envelope_to_mapping", _mismatch
    )
    with pytest.raises(RunStateError) as excinfo:
        emit_equipment_section([dicom_capture], exam_count=1)
    assert excinfo.value.code == CODE_EQUIPMENT_GEOMETRY_MISMATCH


def test_boundary_performs_no_io(dicom_capture: CapturedCoordinates) -> None:
    """Decode and emit never touch files, descriptors, or database handles."""
    section = envelope_to_mapping([dicom_capture, None])

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("boundary must not perform I/O")

    with (
        mock.patch("builtins.open", _refuse),
        mock.patch("io.open", _refuse),
        mock.patch("pathlib.Path.open", _refuse),
        mock.patch("os.open", _refuse),
        mock.patch("sqlite3.connect", _refuse),
    ):
        parsed = decode_equipment_section(copy.deepcopy(section), exam_count=2)
        assert parsed is not None
        emitted = emit_equipment_section(list(parsed), exam_count=2)
    assert emitted == section


def test_modules_stay_gui_light() -> None:
    """The new modules import no pandas or NiceGUI runtime of their own.

    Static scan plus a fresh-interpreter probe: the ``sys.modules`` check
    cannot live in-process because sibling test modules may import NiceGUI
    first, so the probe runs in a subprocess.
    """
    import subprocess

    for name in ("run_state_errors", "run_state_equipment"):
        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "guiskindose"
            / "gui"
            / f"{name}.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "pandas" not in imported
        assert "nicegui" not in imported
    probe = (
        "import sys, guiskindose.gui.run_state_equipment as m; "
        "assert 'nicegui' not in sys.modules; "
        "assert 'guiskindose.gui.app' not in sys.modules; "
        "assert set(m.__all__) == {'PendingEntry', 'build_pending', "
        "'decode_equipment_section', 'emit_equipment_section', "
        "'equipment_section_for_document', 'publish_restored_captures', "
        "'revalidate_pending', 'translate_capture_error', "
        "'validate_equipment_document', 'warn_equipment_import'}"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0


class _HostileMode:
    def __eq__(self, other: object) -> bool:
        raise RuntimeError("PRIVATE MODE SENTINEL")


class _EqualMode:
    def __eq__(self, other: object) -> bool:
        return True


@pytest.mark.parametrize("mode", [_HostileMode(), _EqualMode()])
def test_decode_requires_exact_string_mode(mode: Any) -> None:
    section = {"schema_version": 1, "mode": mode, "captures": []}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=0)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "SENTINEL" not in str(excinfo.value)
    assert "Exam" not in str(excinfo.value)


def test_decode_colliding_hostile_key_never_equated() -> None:
    key = _HostileText("mode", hash("mode"))
    section = {"schema_version": 1, key: "coordinates", "captures": []}
    with pytest.raises(RunStateError) as excinfo:
        decode_equipment_section(section, exam_count=0)
    assert excinfo.value.code == CODE_INVALID_EQUIPMENT_CAPTURE
    assert "Exam" not in str(excinfo.value)


def test_trial_settings_error_does_not_expose_exception(monkeypatch):
    from guiskindose.gui.run_state_trial import _trial_apply_settings
    from guiskindose.gui.state import AppState

    def fail_build(_state):
        raise ValueError("PRIVATE SETTINGS SENTINEL")

    monkeypatch.setattr("guiskindose.gui.settings_builder.build_settings", fail_build)
    state = AppState()
    with pytest.raises(RunStateError) as caught:
        _trial_apply_settings({}, None, state)
    assert caught.value.code == "invalid_settings"
    assert str(caught.value) == "Imported settings failed validation."
    assert caught.value.__suppress_context__ is True
