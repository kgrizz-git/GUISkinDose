"""
GUI smoke tests for MyPySkinDose NiceGUI app (Harness Phase 5).

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
    await user.should_see("MyPySkinDose")
    await user.should_see("1 · Upload")
    await user.should_see("Run Calculation")
