"""
GUI smoke tests for the GUISkinDose NiceGUI app (Harness Phase 5).

Verifies the production page module loads and the primary index route renders
key UI chrome using NiceGUI user simulation (no browser).
"""

from __future__ import annotations

import pytest
from nicegui.testing import User

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


def test_gui_module_imports() -> None:
    """GUI package and page module import without starting ui.run()."""
    import guiskindose.gui  # noqa: F401
    import guiskindose.gui.app as gui_app

    assert gui_app.GUI_VERSION
    assert callable(gui_app.run_gui)


@pytest.mark.asyncio
async def test_index_page_renders(user: User) -> None:
    """Primary '/' route shows app title and first workflow tab."""
    await user.open("/")
    await user.should_see("GUISkinDose")
    await user.should_see("1 · Upload")
    await user.should_see("Run Calculation")


@pytest.mark.asyncio
async def test_onboarding_dialog_shows_intended_use_disclaimer(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    """The startup dialog leads with the not-FDA-cleared / clinician-responsibility notice."""
    import guiskindose.gui.app as gui_app
    from guiskindose.gui.ui_copy import copy_text

    monkeypatch.setattr(gui_app, "is_onboarding_dismissed", lambda: False)
    monkeypatch.setattr(gui_app, "is_intended_use_acknowledged", lambda: False)
    await user.open("/")
    await user.should_see("Welcome to GUISkinDose", retries=20)
    await user.should_see(copy_text("onboarding.intended_use"))


@pytest.mark.asyncio
async def test_dismissed_onboarding_still_shows_unacknowledged_notice(
    user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upgrading installs that turned onboarding off still see the notice once."""
    import guiskindose.gui.app as gui_app
    from guiskindose.gui.ui_copy import copy_text

    monkeypatch.setattr(gui_app, "is_onboarding_dismissed", lambda: True)
    monkeypatch.setattr(gui_app, "is_intended_use_acknowledged", lambda: False)
    await user.open("/")
    await user.should_see(copy_text("onboarding.intended_use"), retries=20)


@pytest.mark.asyncio
async def test_no_dialog_once_dismissed_and_acknowledged(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    import guiskindose.gui.app as gui_app

    monkeypatch.setattr(gui_app, "is_onboarding_dismissed", lambda: True)
    monkeypatch.setattr(gui_app, "is_intended_use_acknowledged", lambda: True)
    await user.open("/")
    await user.should_see("1 · Upload", retries=20)
    await user.should_not_see("Welcome to GUISkinDose")


@pytest.mark.asyncio
async def test_results_tab_shows_intended_use_line(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Results tab keeps a short, non-dismissible intended-use line."""
    import guiskindose.gui.app as gui_app
    from guiskindose.gui.ui_copy import copy_text

    monkeypatch.setattr(gui_app, "is_onboarding_dismissed", lambda: True)
    monkeypatch.setattr(gui_app, "is_intended_use_acknowledged", lambda: True)
    await user.open("/")
    await user.should_see("6 · Results", retries=20)
    user.find("6 · Results").click()
    await user.should_see(copy_text("results.intended_use"), retries=20)


@pytest.mark.asyncio
async def test_got_it_persists_dismissal_and_acknowledgment(
    user: User, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Clicking through the real dialog records both choices, and it stays hidden on reload."""
    import json

    from guiskindose.gui import onboarding, window_prefs

    target = tmp_path / "gui.json"
    monkeypatch.setattr(window_prefs, "config_path", lambda: target)
    monkeypatch.setattr(window_prefs, "new_config_path", lambda: target)

    await user.open("/")
    await user.should_see("Welcome to GUISkinDose", retries=20)
    user.find("Don't show this again").click()
    user.find("Got it").click()

    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored[onboarding.ONBOARDING_KEY] is True
    assert stored[onboarding.INTENDED_USE_ACK_KEY] == onboarding.INTENDED_USE_NOTICE_VERSION

    await user.open("/")
    await user.should_see("1 · Upload", retries=20)
    await user.should_not_see("Welcome to GUISkinDose")
