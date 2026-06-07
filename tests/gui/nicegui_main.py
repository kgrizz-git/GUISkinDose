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

import mypyskindose.gui.app as gui_app  # noqa: E402 — prepare_simulation() must run first

importlib.reload(gui_app)
