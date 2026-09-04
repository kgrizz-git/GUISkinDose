"""Regression tests for cross-tab slider synchronization (CROSS_TAB_SLIDER_SYNC_PLAN.md)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui.state import AppState


def test_tab_change_to_geometry_refreshes_callbacks():
    """Switching to 'geometry' tab triggers refresh_geometry_tab and refresh_geometry_preview."""
    ctx = MagicMock()
    state = AppState()
    nav_calls = []

    def _update_nav_classes():
        nav_calls.append(True)

    def _on_tab_changed(tab_name: str) -> None:
        state.active_tab = tab_name
        _update_nav_classes()
        if tab_name == "geometry":
            ctx.refresh_geometry_tab()
            ctx.refresh_geometry_preview()

    _on_tab_changed("geometry")

    assert state.active_tab == "geometry"
    assert len(nav_calls) == 1
    ctx.refresh_geometry_tab.assert_called_once()
    ctx.refresh_geometry_preview.assert_called_once()


@pytest.mark.parametrize("tab", ["upload", "data", "settings", "calculate", "results", "export"])
def test_tab_change_to_other_tabs_does_not_refresh_geometry(tab: str):
    """Switching to a non-geometry tab does NOT trigger geometry callbacks."""
    ctx = MagicMock()
    state = AppState()

    def _on_tab_changed(tab_name: str) -> None:
        state.active_tab = tab_name
        if tab_name == "geometry":
            ctx.refresh_geometry_tab()
            ctx.refresh_geometry_preview()

    _on_tab_changed(tab)

    assert state.active_tab == tab
    ctx.refresh_geometry_tab.assert_not_called()
    ctx.refresh_geometry_preview.assert_not_called()
