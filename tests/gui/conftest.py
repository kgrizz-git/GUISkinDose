"""
Pytest configuration for NiceGUI smoke tests (Harness Phase 5).

Requires: pip install -e '.[gui]'  (includes pytest-asyncio)

The NiceGUI test plugin (which provides the `user` fixture) is registered in the
top-level tests/conftest.py — pytest no longer allows `pytest_plugins` in a
nested conftest. This file just skips the GUI tests when NiceGUI is absent.
"""

from __future__ import annotations

import sys
from contextlib import suppress
from types import ModuleType

import importlib.util
import logging
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from nicegui.testing.general_fixtures import get_path_to_main_file
from nicegui.testing.user_simulation import user_simulation

_ERRORS_PATH = Path(__file__).with_name("expected_gui_errors.py")
_ERRORS_SPEC = importlib.util.spec_from_file_location("expected_gui_errors", _ERRORS_PATH)
assert _ERRORS_SPEC is not None and _ERRORS_SPEC.loader is not None
_ERRORS = importlib.util.module_from_spec(_ERRORS_SPEC)
sys.modules[_ERRORS_SPEC.name] = _ERRORS
_ERRORS_SPEC.loader.exec_module(_ERRORS)
drop_allowed_gui_errors = _ERRORS.drop_allowed_gui_errors


def _cancel_leaked_timers() -> None:
    """Cancel every NiceGUI ``ui.timer`` still alive across all clients.

    Several tabs start repeating timers at build time (data/settings/results
    refresh loops). NiceGUI's ``User`` test harness builds a fresh page per test
    but does not tear down the previous page's timers, so without this they keep
    firing into the event loop for the rest of the session — starving the
    debounce/render timing the geometry-slider tests assert on, and making
    later tests in the suite flaky and order-dependent.
    """
    from nicegui import Client
    from nicegui.elements.timer import Timer

    for client in list(Client.instances.values()):
        for element in list(client.elements.values()):
            if isinstance(element, Timer):
                with suppress(Exception):  # pragma: no cover - best-effort teardown
                    element.cancel()


def _reset_state_singleton() -> None:
    """Reset the module-level ``AppState`` singleton in place.

    ``guiskindose.gui.state.state`` is a shared singleton that most GUI modules
    import by reference, so reassigning it would not update those references.
    Copying a fresh instance's ``__dict__`` resets every field in place, giving
    each test a clean slate (no leaked ``rdsr_df`` / offsets / multi-exam flags).
    """
    from guiskindose.gui.state import AppState, state

    state.__dict__.clear()
    state.__dict__.update(AppState().__dict__)


def _guiskindose_modules() -> dict[str, ModuleType]:
    return {name: module for name, module in sys.modules.items() if name.partition(".")[0] == "guiskindose"}


@pytest.fixture(autouse=True)
def _restore_popped_package_modules():
    """Put back the ``guiskindose`` packages NiceGUI's ``user`` fixture evicts.

    On teardown, NiceGUI pops each page-route module *and all its parents* from
    ``sys.modules`` (``guiskindose.gui.app``, ``guiskindose.gui``, ``guiskindose``)
    but leaves their other submodules behind. The next import then builds fresh
    parent packages that lack those submodules as attributes, so a later test's
    ``monkeypatch.setattr("guiskindose.gui.run_state_equipment.x", ...)`` fails with
    ``module 'guiskindose.gui' has no attribute ...``. Main CI never saw it because
    it runs ``tests/gui`` in its own process; a single ``pytest`` run of the whole
    suite (as ci-latest does) did. Autouse, so it is set up before ``user`` and its
    teardown runs after NiceGUI's.
    """
    before = _guiskindose_modules()
    yield
    for name, module in before.items():
        sys.modules.setdefault(name, module)


@pytest.fixture(autouse=True)
def _isolate_gui_state():
    """Give every GUI test a clean shared state and no leaked timers.

    Runs before each test (so a test never inherits the previous one's state or
    still-firing timers) and again after, keeping the session tidy.
    """
    _cancel_leaked_timers()
    _reset_state_singleton()
    yield
    _cancel_leaked_timers()
    _reset_state_singleton()


@pytest.fixture(autouse=True)
def _isolate_loopback_security(monkeypatch):
    """Keep ``run_gui()`` side effects out of the simulation suite.

    ``run_gui()`` registers ASGI middleware and installs a per-launch token
    config on the process-global NiceGUI app; the user-simulation tests never
    call ``run_gui()`` and must see neither. No-op the registrations and reset
    the config around every test (individual tests re-patch what they assert).
    """
    import guiskindose.gui.app as gui_app
    from guiskindose.gui.loopback_security import configure_loopback_security

    monkeypatch.setattr(gui_app.app, "add_middleware", lambda *args, **kwargs: None)
    monkeypatch.setattr(gui_app, "_open_browser_when_ready", lambda *args, **kwargs: None)
    # NOTE: _static_files_registration is intentionally not reset here. The
    # user-simulation harness reloads gui.app, so this fixture's module
    # reference may differ from the one test modules hold. Tests that need a
    # clean guard monkeypatch ``.registered`` on their own reference so pytest
    # restores the previous value when the test ends.
    configure_loopback_security(None)
    yield
    configure_loopback_security(None)


@pytest.fixture
async def user(caplog: pytest.LogCaptureFixture, request: pytest.FixtureRequest):
    """Same simulation as NiceGUI's fixture, after dropping allowlisted call-phase ERRORs.

    Shadows ``nicegui.testing.user_plugin.user`` for tests under ``tests/gui`` only.
    NiceGUI 3.18 checks ``caplog.get_records('call')`` inside the ``async with``,
    after ``yield`` and before ``user_simulation`` exits. The filter has to run
    in that same place. Logs emitted while the context exits are teardown-phase
    records and are not part of this check.
    """
    async with user_simulation(main_file=get_path_to_main_file(request)) as simulated:
        yield simulated
        # Stop tab refresh timers before NiceGUI tears the client down. Autouse
        # ``_isolate_gui_state`` cancels them only after this fixture finishes;
        # on pytest 9.1 that ordering leaves repeating timers (e.g. results
        # dose-map refresh) runnable while ``user_simulation`` waits on asyncio
        # shutdown and the session hangs.
        _cancel_leaked_timers()
        call_records = caplog.get_records("call")
        drop_allowed_gui_errors(call_records)
        errors = [record for record in call_records if record.levelname == "ERROR"]
        if errors:
            pytest.fail("There were unexpected ERROR logs.", pytrace=False)
