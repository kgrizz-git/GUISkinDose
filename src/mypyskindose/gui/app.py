"""MyPySkinDose — NiceGUI app entry point.

Run with:
    python src/mypyskindose/main.py --mode gui
or directly:
    .venv/Scripts/python -m mypyskindose --mode gui
    .venv/Scripts/python -m mypyskindose --mode gui --native
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

# Fix for Windows SSL context loading error during shutdown
os.environ["SSL_CERT_FILE"] = ""

# Fix for colorama atexit error on Windows during shutdown
os.environ["COLORAMA_DISABLE"] = "1"

from nicegui import Client, app, ui

from mypyskindose.debug import configure_logging, dprint

from .page_context import PageContext
from .styles import MODERN_CSS
from .state import state
from .tabs import calculate as calculate_tab
from .tabs import data as data_tab
from .tabs import export as export_tab
from .tabs import geometry as geometry_tab
from .tabs import results as results_tab
from .tabs import settings as settings_tab
from .tabs import upload as upload_tab

GUI_VERSION = "1.1.0"


# ── page ───────────────────────────────────────────────────────────────────
@ui.page("/")
def index():
    dprint("GUI", f"Rendering index page (v{GUI_VERSION})")

    ui.colors(primary="#2563EB", secondary="#2563EB", accent="#831843", positive="#064E3B")
    ui.add_head_html(f"<style>{MODERN_CSS}</style>")
    ui.add_head_html(
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,300,0,0" />'
    )
    ui.dark_mode(True)

    with ui.header().classes("items-center justify-between px-6 py-2 modern-header"):
        with ui.row().classes("items-center gap-3"):
            ui.label("MyPySkinDose").classes("text-h6 font-bold text-white")
            ui.label(f"v{GUI_VERSION}").style(
                "color: #F8FAFC; font-weight: bold; font-size: 10px; opacity: 0.3; margin-top: 4px;"
            )
        with ui.row().classes("items-center gap-6"):
            ui.button(icon="menu", on_click=lambda: left_drawer.toggle()).props(
                "flat round color=white"
            ).classes("icon-outlined")

    with ui.left_drawer(fixed=True).classes("q-pa-md") as left_drawer:
        ui.label("Status").classes("text-caption text-grey-6 q-mb-xs")
        with ui.column().classes("gap-0 q-mb-sm"):
            file_label = ui.label("No file loaded").classes("text-caption")
            events_label = ui.label("0 events").classes("text-caption")
            psd_label = ui.label("PSD: 0.00 mGy").classes("text-h6 text-pink-5 font-bold q-mt-xs")
        ui.separator().classes("q-my-sm bg-zinc-800")
        ui.label("Navigation").classes("text-caption text-grey-6 q-mb-0")

        def go(name: str):
            tabs.set_value(name)
            state.active_tab = name
            _update_nav_classes()

        def _update_nav_classes():
            for btn, target in nav_buttons:
                if state.active_tab == target:
                    btn.classes(add="active", remove="text-grey-4")
                else:
                    btn.classes(remove="active", add="text-grey-4")

        nav_buttons: list[tuple[ui.button, str]] = []

        def nav_btn(label: str, target: str) -> ui.button:
            btn = ui.button(label, on_click=lambda: go(target)).props(
                "flat align=left dense no-caps"
            ).classes("nav-item full-width text-left py-2 text-grey-4")
            nav_buttons.append((btn, target))
            return btn

        nav_btn("1 · Upload", "upload")
        nav_btn("2 · Data Table", "data")
        nav_btn("3 · Settings", "settings")
        nav_btn("4 · Geometry", "geometry")
        nav_btn("5 · Calculate", "calculate")
        nav_btn("6 · Results", "results")
        nav_btn("7 · Export", "export")
        ui.separator().classes("q-my-md bg-zinc-800")
        run_btn_drawer = ui.button("Run Calculation", icon="play_arrow").classes(
            "full-width modern-btn icon-outlined"
        )

    with ui.tabs().classes("w-full").on(
        "update:model-value", lambda e: setattr(state, "active_tab", e.args)
    ) as tabs:
        ui.tab("upload", label="1 · Upload")
        ui.tab("data", label="2 · Data Table")
        ui.tab("settings", label="3 · Settings")
        ui.tab("geometry", label="4 · Geometry")
        ui.tab("calculate", label="5 · Calculate")
        ui.tab("results", label="6 · Results")
        ui.tab("export", label="7 · Export")

    ctx = PageContext(
        tabs=tabs,
        file_label=file_label,
        events_label=events_label,
        psd_label=psd_label,
        run_btn_drawer=run_btn_drawer,
    )

    with ui.tab_panels(tabs, value="upload").classes("w-full bg-transparent"):
        upload_tab.build(ctx)
        data_tab.build(ctx)
        settings_tab.build(ctx)
        geometry_tab.build(ctx)
        calculate_tab.build(ctx)
        results_tab.build(ctx)
        export_tab.build(ctx)

    if state.rdsr_df is not None:
        dprint("GUI", "Restoring UI state from loaded data")
        ctx.file_label.set_text(state.file_name.upper())
        ctx.events_label.set_text(f"{len(state.rdsr_df)} EVENTS")
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        if state.active_tab:
            ctx.tabs.set_value(state.active_tab)


# ── entry point ────────────────────────────────────────────────────────────


def run_gui(native: bool = False, host: str | None = None) -> None:
    """Launch the MyPySkinDose NiceGUI app.

    Binds to 127.0.0.1 (localhost only) by default. The GUI has no authentication
    and loads PHI-derived RDSR data into a single process-global, shared state, so
    it must not be exposed on the network unintentionally — and NiceGUI's browser
    mode would otherwise default to 0.0.0.0 (all interfaces). Pass an explicit
    ``host`` (e.g. ``"0.0.0.0"``) to opt into LAN serving; only do so on a trusted
    network and behind your own access controls.
    """
    log_file = None
    if native:
        log_file = Path(tempfile.gettempdir()) / "mypyskindose-gui.log"
    configure_logging(log_file=log_file)
    dprint("GUI", f"Starting run_gui, native={native}")
    if native:
        dprint("GUI", f"Logging to {log_file}")

    if native:

        @app.on_connect
        def _handle_native_focus():
            try:
                if app.native.main_window is not None:
                    set_on_top = getattr(app.native.main_window, "set_on_top", None)
                    if callable(set_on_top):
                        set_on_top(True)
            except Exception as exc:
                dprint("GUI", f"Native window focus failed: {exc}")

    import logging

    logging.getLogger("nicegui").setLevel(logging.ERROR)

    if not native:

        @app.on_disconnect
        def _shutdown_when_last_window_closes() -> None:
            async def _shutdown_if_idle() -> None:
                await asyncio.sleep(4.0)
                if not any(c.has_socket_connection for c in Client.instances.values()):
                    dprint("GUI", "Last browser window closed; shutting down server.")
                    app.shutdown()

            asyncio.create_task(_shutdown_if_idle())

    window_size: tuple[int, int] | None = None
    if native:
        try:
            import tkinter as tk

            _root = tk.Tk()
            _root.withdraw()
            sw, sh = _root.winfo_screenwidth(), _root.winfo_screenheight()
            _root.destroy()
            window_size = (int(sw * 0.75), int(sh * 0.75))
        except Exception as exc:
            dprint(
                "GUI",
                f"Could not detect screen size ({exc}); using default window size. "
                "Install Tkinter for screen-size detection and native Save As dialogs "
                "— see the 'native Save As dialogs (Tkinter)' note in README.md.",
            )

    bind_host = host or "127.0.0.1"
    if bind_host not in ("127.0.0.1", "localhost"):
        dprint(
            "GUI",
            f"Binding GUI to {bind_host} — exposed beyond localhost with no "
            "authentication; ensure this is a trusted network.",
        )

    try:
        ui.run(
            title="MyPySkinDose",
            native=native,
            host=bind_host,
            window_size=window_size,
            reload=False,
            port=8765,
            show=True,
            favicon="🩻",
            reconnect_timeout=30.0,
        )
    except KeyboardInterrupt:
        dprint("GUI", "Interrupted (Ctrl+C); shutting down.")


if __name__ == "__main__":
    run_gui()
