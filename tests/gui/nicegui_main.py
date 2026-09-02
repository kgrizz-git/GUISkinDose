"""
NiceGUI pytest entry module (Harness Phase 5).

Loaded by NiceGUI user simulation via runpy. Registers run config and loads
production page routes without calling ui.run().

Uses importlib.reload so @ui.page decorators re-run after the user fixture
clears NiceGUI global state (sys.modules cache would otherwise skip registration).
"""

from __future__ import annotations

import importlib

from nicegui.testing.general import prepare_simulation

prepare_simulation()

# This must stay after prepare_simulation(), which initializes the user-test state.
import guiskindose.gui.app as gui_app

importlib.reload(gui_app)
