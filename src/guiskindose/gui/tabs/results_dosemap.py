"""Single-exam dose map for the Results tab: the real map, or a zero-dose phantom before any calculation.

``state`` is shared by every browser tab, while each page has its own controller, so what this
page has drawn is tracked here rather than read back from ``state``.
"""

from __future__ import annotations

from typing import Any

from nicegui import run

from ..figures import make_dosemap_fig
from ..phantom_preview import capture_phantom_preview_snapshot, make_placeholder_dosemap_fig
from ..state import state
from .results_view_refs import ResultsViewRefs


class SingleExamDosemapMixin:
    """Dose-map drawing for ``ResultsTabController``."""

    refs: ResultsViewRefs

    def _init_dosemap_state(self) -> None:
        # Inputs of the zero-dose placeholder now on screen; None while it is not shown.
        self._placeholder_key: tuple[Any, str] | None = None
        # Calculation run whose real map this page shows.
        self._dosemap_run_id: int | None = None
        # True while any figure (real map or placeholder) is on the plot.
        self._dosemap_drawn = False
        # Bumped by each placeholder build; only the newest may draw.
        self._placeholder_request_id = 0

    def _show_dosemap(self, fig: dict, placeholder_key: tuple[Any, str] | None) -> None:
        """Put a figure on the single-exam plot; the caption shows only over a placeholder."""
        self.refs.dosemap_plot.update_figure(fig)
        self._dosemap_drawn = True
        self._placeholder_key = placeholder_key
        self._set_placeholder_caption(placeholder_key is not None)

    def _clear_dosemap(self) -> None:
        """Empty the single-exam plot so nothing stale stays on screen."""
        if self._dosemap_drawn:
            self.refs.dosemap_plot.update_figure({})
        self._dosemap_drawn = False
        self._placeholder_key = None
        self._dosemap_run_id = None
        self._set_placeholder_caption(False)

    def _set_placeholder_caption(self, visible: bool) -> None:
        if self.refs.dosemap_placeholder_caption is not None:
            self.refs.dosemap_placeholder_caption.visible = visible

    def _clear_stale_figure(self, run_id: int) -> None:
        """Empty a placeholder, or a real map of another run, before building ``run_id``'s map.

        A real map of the run being redrawn (colour-scale change, REGENERATE) is left on
        screen while its replacement builds, so the panel never flashes empty. The
        placeholder key is only dropped when the placeholder itself is cleared, which
        keeps it describing exactly what is displayed.
        """
        stale_run = self._dosemap_drawn and self._dosemap_run_id != run_id
        if self._placeholder_key is not None or stale_run:
            self._clear_dosemap()

    async def refresh_dosemap(self) -> None:
        """Redraw the dose map: the real map after a calculation, the zero-dose phantom before."""
        if state.is_multi_exam:
            return
        if not state.calculation_done:
            await self.refresh_placeholder_dosemap(force=True)
            return
        run_id = state.calc_run_id
        # A zero-dose phantom, or a map from a superseded run, must not stand in for this run.
        self._clear_stale_figure(run_id)
        self.refs.dosemap_spinner.visible = True
        try:
            fig = await run.io_bound(make_dosemap_fig)
        finally:
            self.refs.dosemap_spinner.visible = False
        # Drop a figure whose run was invalidated or superseded while it was being built.
        if fig and state.calculation_done and state.calc_run_id == run_id:
            self._dosemap_run_id = run_id
            self._show_dosemap(fig, None)

    async def maybe_auto_refresh_dosemap(self) -> None:
        """Show the real dose map once calculated, and a zero-dose phantom before that."""
        if state.is_multi_exam:
            return
        if state.calculation_done:
            if self._dosemap_run_id != state.calc_run_id:
                # A different run (or a placeholder) must not pass for this run's result.
                await self.refresh_dosemap()
            return
        if self._dosemap_run_id is not None:
            # The real map on screen belongs to an invalidated run.
            self._clear_dosemap()
        await self.refresh_placeholder_dosemap()

    async def refresh_placeholder_dosemap(self, force: bool = False) -> None:
        """Draw the selected phantom with no dose, redrawing only when phantom or colorscale change."""
        snapshot = capture_phantom_preview_snapshot(state)
        key = (snapshot, str(state.colorscale))
        if not force and key == self._placeholder_key:
            return
        self._placeholder_request_id += 1
        request_id = self._placeholder_request_id
        fig = await run.io_bound(make_placeholder_dosemap_fig, snapshot, key[1])
        # A newer build (colour-scale change, REGENERATE) started meanwhile, or a calculation finished.
        if request_id != self._placeholder_request_id or state.calculation_done:
            return
        # The phantom or colour scale changed while the mesh built, so this figure is stale.
        if key != (capture_phantom_preview_snapshot(state), str(state.colorscale)):
            return
        # Remember the key only on success, so a mesh that fails now (for example one not yet
        # installed) is retried on the next tick instead of being latched as drawn.
        if fig:
            self._show_dosemap(fig, key)
        else:
            # Never leave the previous figure on screen for a selection that cannot be drawn.
            self._clear_dosemap()
