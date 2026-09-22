"""
Pytest configuration for NiceGUI smoke tests (Harness Phase 5).

Requires: pip install -e '.[gui]'  (includes pytest-asyncio)

The NiceGUI test plugin (which provides the `user` fixture) is registered in the
top-level tests/conftest.py — pytest no longer allows `pytest_plugins` in a
nested conftest. This file just skips the GUI tests when NiceGUI is absent.
"""

from __future__ import annotations

from contextlib import suppress

import pytest

pytest.importorskip("nicegui")


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
    configure_loopback_security(None)
    yield
    configure_loopback_security(None)
