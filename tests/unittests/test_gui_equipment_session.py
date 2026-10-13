"""GUI live coordinate-session ownership: bind seam, settings binding, privacy."""

from __future__ import annotations

from typing import Any

import pytest

from guiskindose.equipment_profiles import FileSource, assemble_session
from guiskindose.gui.settings_builder import bind_equipment_session, build_settings
from guiskindose.gui.state import AppState


def _profile_doc(profile_id: str) -> dict[str, Any]:
    """Single memory profile matching the approved Siemens fixture."""
    return {
        "schema_version": 1,
        "profiles": [
            {
                "profile_id": profile_id,
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
def session() -> Any:
    """Assembled immutable memory session (no files opened)."""
    return assemble_session(documents=[_profile_doc("gui-session")])



def test_build_settings_binds_none_by_default() -> None:
    """No session home means bundled/Default resolution, as before."""
    settings = build_settings(AppState())
    assert settings.equipment_profile_session is None


def test_build_settings_binds_live_session(session: Any) -> None:
    """The bound session object itself reaches the settings, never a copy."""
    state = AppState()
    state.equipment_profile_session = session
    settings = build_settings(state)
    assert settings.equipment_profile_session is session


def test_bind_refuses_mistyped_session() -> None:
    """Only assembled sessions or None may occupy the home."""
    state = AppState()
    bogus: Any = "session"
    with pytest.raises(ValueError, match="EquipmentProfileSession or None"):
        bind_equipment_session(state, bogus)
    assert state.equipment_profile_session is None


def test_bind_refuses_with_loaded_exams(session: Any) -> None:
    """Activation under loaded geometry is refused before any mutation."""
    state = AppState()
    state.loaded_exams.append(object())
    state.psd = 1.5
    with pytest.raises(ValueError, match="unload all exams first"):
        bind_equipment_session(state, session)
    assert state.equipment_profile_session is None
    assert state.loaded_exams != []
    assert state.psd == 1.5


def test_bind_replacement_refused_with_loaded_exams(session: Any) -> None:
    """Replacement is activation too: loaded exams block it identically."""
    state = AppState()
    state.loaded_exams.append(object())
    with pytest.raises(ValueError, match="unload all exams first"):
        bind_equipment_session(state, None)
    assert state.loaded_exams != []


def test_bind_refuses_busy_state(session: Any) -> None:
    """An in-flight operation blocks binding before any mutation."""
    state = AppState()
    state.busy = True
    state.psd = 1.0
    state.d_lon = 2.0
    with pytest.raises(ValueError, match="in flight"):
        bind_equipment_session(state, session)
    assert state.equipment_profile_session is None
    assert state.psd == 1.0
    assert state.d_lon == 2.0


def test_bind_refuses_legacy_preview_state(session: Any) -> None:
    """A set preview frame means loaded geometry even with no exam entries."""
    import pandas as pd

    state = AppState()
    state.rdsr_df = pd.DataFrame({"Tx": [1.0]})
    state.psd = 1.0
    state.d_lon = 2.0
    with pytest.raises(ValueError, match="preview"):
        bind_equipment_session(state, session)
    assert state.equipment_profile_session is None
    assert state.psd == 1.0
    assert state.d_lon == 2.0


def test_bind_empty_state_succeeds_and_invalidates(session: Any) -> None:
    """Binding on an empty state publishes the home and clears stale results."""
    state = AppState()
    state.psd = 2.5
    state.calculation_done = True
    bind_equipment_session(state, session)
    assert state.equipment_profile_session is session
    assert state.psd is None
    assert state.calculation_done is False


def test_unbind_empty_state_succeeds(session: Any) -> None:
    """Clearing back to None follows the same import-before-load rule."""
    state = AppState()
    bind_equipment_session(state, session)
    bind_equipment_session(state, None)
    assert state.equipment_profile_session is None


def test_bind_session_refuses_pending(session: Any) -> None:
    """Activating with staged entries refuses before any mutation."""
    from guiskindose.gui.run_state_equipment import PendingEntry

    state = AppState()
    state.equipment_pending = (
        PendingEntry(
            capture=None,
            swap_lat_lon=False,
            flip_ap1=False,
            flip_ap2=False,
            flip_tx=False,
            flip_ty=False,
            flip_tz=False,
            d_lon=0.0,
            d_ver=0.0,
            d_lat=0.0,
            table_origin_override=None,
        ),
    )
    state.psd = 1.0
    with pytest.raises(ValueError, match="staged"):
        bind_equipment_session(state, session)
    assert state.equipment_profile_session is None
    assert state.psd == 1.0
    assert state.equipment_pending is not None


def test_unbind_with_pending_allowed(session: Any) -> None:
    """Clearing back to None never conflicts with staged entries."""
    from guiskindose.gui.run_state_equipment import PendingEntry

    state = AppState()
    bind_equipment_session(state, session)
    state.equipment_pending = (
        PendingEntry(
            capture=None,
            swap_lat_lon=False,
            flip_ap1=False,
            flip_ap2=False,
            flip_tx=False,
            flip_ty=False,
            flip_tz=False,
            d_lon=0.0,
            d_ver=0.0,
            d_lat=0.0,
            table_origin_override=None,
        ),
    )
    bind_equipment_session(state, None)
    assert state.equipment_profile_session is None
    assert state.equipment_pending is not None


def test_reset_results_preserves_session_home(session: Any) -> None:
    """Settings-only invalidation never drops the bound session."""
    from guiskindose.gui.state import reset_results

    state = AppState()
    bind_equipment_session(state, session)
    reset_results(state)
    assert state.equipment_profile_session is session


def test_file_source_repr_hides_path() -> None:
    """Session file provenance never renders paths, notes, or sentinels."""
    source = FileSource(path="/secret/station/notes.json", format="json", sheet=0)
    text = repr(source)
    assert "/secret/station/notes.json" not in text
    assert "station" not in text


def test_session_repr_is_counts_only(session: Any) -> None:
    """The session repr carries counts and hashes, never profile content."""
    text = repr(session)
    assert "Siemens" not in text
    assert "AXIOM-Artis" not in text
    assert "gui-session" not in text
    assert session.active_set_hash in text
