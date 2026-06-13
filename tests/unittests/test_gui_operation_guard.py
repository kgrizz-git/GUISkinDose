"""Unit tests for the GUI concurrency guard (refactor plan Phase 0.3).

_operation_guard prevents a second load/sheet-change/calculation from
interleaving its state mutations with one already in flight. These tests pin the
contract: first entry proceeds and sets state.busy, a re-entrant entry is denied,
and state.busy is always cleared on exit (including on exception).
"""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

import mypyskindose.gui.app as gui_app
from mypyskindose.gui.state import state


@pytest.fixture(autouse=True)
def _reset_busy():
    state.busy = False
    yield
    state.busy = False


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch):
    """The denied-entry branch calls ui.notify, which needs a live client/slot
    context. These tests assert only the busy-flag contract, so stub it out —
    otherwise they break depending on whether a prior GUI-simulation test has
    cleared NiceGUI's slot stack (a test-ordering artifact, not app behavior)."""
    monkeypatch.setattr(gui_app.ui, "notify", lambda *a, **k: None)


def test_first_entry_proceeds_and_sets_busy():
    with gui_app._operation_guard("x") as proceed:
        assert proceed is True
        assert state.busy is True
    assert state.busy is False  # cleared on exit


def test_reentrant_entry_is_denied():
    with gui_app._operation_guard("outer") as outer:
        assert outer is True
        with gui_app._operation_guard("inner") as inner:
            assert inner is False, "second operation must be denied while busy"
        # busy stays True while the outer operation is still running
        assert state.busy is True
    assert state.busy is False


def test_busy_cleared_on_exception():
    with pytest.raises(RuntimeError):
        with gui_app._operation_guard("boom") as proceed:
            assert proceed is True
            assert state.busy is True
            raise RuntimeError("boom")
    assert state.busy is False, "busy must be cleared even when the body raises"


def test_denied_entry_does_not_clear_outer_busy():
    """A denied re-entrant guard must not flip busy off when it exits."""
    state.busy = True
    with gui_app._operation_guard("denied") as proceed:
        assert proceed is False
    assert state.busy is True  # the in-flight operation's flag is untouched


def test_sequential_operations_each_proceed():
    for _ in range(3):
        with gui_app._operation_guard("seq") as proceed:
            assert proceed is True
        assert state.busy is False
