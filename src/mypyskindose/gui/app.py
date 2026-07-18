"""MyPySkinDose — NiceGUI app entry point.

Run with:
    python src/mypyskindose/main.py --mode gui
or directly:
    .venv/Scripts/python -m mypyskindose --mode gui
    .venv/Scripts/python -m mypyskindose --mode gui --native
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from textwrap import dedent
from typing import Any, cast

# Fix for colorama atexit error on Windows during shutdown
os.environ["COLORAMA_DISABLE"] = "1"

from nicegui import Client, app, ui
from nicegui.events import NativeEventArguments

from mypyskindose.privacy import opaque_exam_label, safe_error_event

from mypyskindose.debug import configure_logging, dprint

from .notifications import install_notification_defaults
from .onboarding import dismiss_onboarding, is_onboarding_dismissed
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
from .ui_copy import copy_text
from .window_prefs import (
    NativeWindowPrefs,
    ScreenBounds,
    default_normal_bounds,
    geometry_looks_maximized,
    load_native_window_prefs,
    primary_screen,
    save_native_window_prefs,
    validate_prefs,
)

logger = logging.getLogger(__name__)

GUI_VERSION = "1.1.0"


# ── page ───────────────────────────────────────────────────────────────────
@ui.page("/")
def index():
    dprint("GUI", f"Rendering index page (v{GUI_VERSION})")

    install_notification_defaults()

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

    nav_buttons: list[tuple[ui.button, str]] = []

    def _update_nav_classes():
        for btn, target in nav_buttons:
            if state.active_tab == target:
                btn.classes(add="active", remove="text-grey-4")
            else:
                btn.classes(remove="active", add="text-grey-4")

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

    def _on_tab_changed(tab_name: str) -> None:
        state.active_tab = tab_name
        _update_nav_classes()
        if tab_name == "geometry":
            ctx.refresh_geometry_tab()
            ctx.refresh_geometry_preview()

    with ui.tabs().classes("w-full").on(
        "update:model-value", lambda e: _on_tab_changed(e.args)
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
        n_exams = len(state.loaded_exams)
        if n_exams <= 1:
            ctx.file_label.set_text(opaque_exam_label(0).upper() if n_exams == 1 else "No file loaded")
        else:
            ctx.file_label.set_text(f"{n_exams} FILES")
        ctx.events_label.set_text(f"{len(state.rdsr_df)} EVENTS")
        ctx.refresh_event_table()
        ctx.refresh_exams_table()
        if state.active_tab:
            ctx.tabs.set_value(state.active_tab)

    if not is_onboarding_dismissed():
        with ui.dialog().props("persistent") as dialog, ui.card().classes(
            "modern-card w-full max-w-md max-h-[80vh] p-6"
        ):
            with ui.row().classes("w-full justify-between items-center q-mb-sm"):
                ui.label("Welcome to MyPySkinDose").classes("text-h5")

            with ui.scroll_area().classes("w-full"):
                ui.markdown(
                    dedent(
                        f"""
                        MyPySkinDose estimates peak skin dose from fluoroscopic X-ray procedures.

                        **1. Upload** — Drag-and-drop a DICOM RDSR (`.dcm`) file, or import
                        CSV/TSV/XLSX data.

                        **2. Settings** — Choose a phantom model and adjust physics parameters
                        (defaults usually work).

                        **3. Geometry** — Preview beam geometry before calculating.

                        **4. Calculate** — Run the dose calculation.

                        **5. Results** — View the 3D dose map and peak skin dose (PSD).

                        **6. Export** — Download results as JSON, HTML, or PNG.

                        **Privacy** — {copy_text("onboarding.privacy_notice")}
                        """
                    ).strip()
                )
            dont_show = ui.checkbox("Don't show this again").classes("q-mt-md")

            def on_ok() -> None:
                if dont_show.value:
                    dismiss_onboarding()
                dialog.close()

            with ui.row().classes("justify-end q-mt-md w-full"):
                ui.button("Got it", on_click=on_ok).classes("modern-btn-primary text-white")

        ui.timer(0.1, dialog.open, once=True)


# ── native window geometry ───────────────────────────────────────────────────


def _detect_native_screens() -> list[ScreenBounds]:
    screens: list[ScreenBounds] = []
    if sys.platform == "darwin":
        try:
            import AppKit  # pyright: ignore[reportMissingImports]  # optional gui-native dep (pyobjc)

            ns_screen = cast(Any, getattr(AppKit, "NSScreen"))
            main_screen = ns_screen.mainScreen()
            screens = [
                ScreenBounds(
                    int(s.frame().origin.x),
                    int(s.frame().origin.y),
                    int(s.frame().size.width),
                    int(s.frame().size.height),
                    is_primary=(s == main_screen),
                )
                for s in ns_screen.screens()
            ]
        except Exception as exc:
            safe_error_event(logger, "appkit_screen_detection", exc, level=logging.DEBUG)
    try:
        if not screens:
            import webview  # pyright: ignore[reportMissingImports]  # optional gui-native dep (pywebview)

            screens = [
                ScreenBounds(
                    s.x,
                    s.y,
                    s.width,
                    s.height,
                    is_primary=bool(getattr(s, "is_primary", False)),
                )
                for s in webview.screens()
            ]
    except Exception as exc:
        safe_error_event(logger, "native_screen_detection", exc, level=logging.DEBUG)
    if not screens:
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.destroy()
            screens = [ScreenBounds(0, 0, sw, sh, is_primary=True)]
        except Exception as exc:
            safe_error_event(logger, "tk_screen_detection", exc, level=logging.DEBUG)
    return screens


def _detect_macos_visible_primary_bounds() -> ScreenBounds | None:
    if sys.platform != "darwin":
        return None
    try:
        import AppKit  # pyright: ignore[reportMissingImports]  # optional gui-native dep (pyobjc)

        ns_screen = cast(Any, getattr(AppKit, "NSScreen"))
        screens = list(ns_screen.screens())
        if not screens:
            return None
        main_screen = ns_screen.mainScreen()
        target = main_screen or max(screens, key=lambda s: s.frame().size.width * s.frame().size.height)
        visible = target.visibleFrame()
        return ScreenBounds(
            int(visible.origin.x),
            int(visible.origin.y),
            int(visible.size.width),
            int(visible.size.height),
            is_primary=True,
        )
    except Exception as exc:
        safe_error_event(logger, "appkit_visible_frame", exc, level=logging.DEBUG)
        return None


def _resolve_native_window_prefs(screens: list[ScreenBounds]) -> NativeWindowPrefs:
    raw = load_native_window_prefs()
    if raw is not None:
        return validate_prefs(raw, screens)
    prefs = default_normal_bounds(screens)
    prefs.maximized = True
    return prefs


def _normalize_macos_maximized_startup(
    prefs: NativeWindowPrefs,
    screens: list[ScreenBounds],
) -> NativeWindowPrefs:
    if sys.platform != "darwin" or not prefs.maximized:
        return prefs

    visible = _detect_macos_visible_primary_bounds()
    if visible is not None:
        return NativeWindowPrefs(
            maximized=False,
            width=int(visible.width),
            height=int(visible.height),
            x=int(visible.x),
            y=int(visible.y),
        )

    primary = primary_screen(screens)
    if primary is None:
        fallback = default_normal_bounds(screens)
        return NativeWindowPrefs(
            maximized=False,
            width=fallback.width,
            height=fallback.height,
            x=fallback.x,
            y=fallback.y,
        )

    width = int(primary.width * 0.9)
    height = int(primary.height * 0.9)
    x = int(primary.x + (primary.width - width) // 2)
    y = int(primary.y + (primary.height - height) // 2)
    return NativeWindowPrefs(
        maximized=False,
        width=width,
        height=height,
        x=x,
        y=y,
    )


def _register_native_geometry_tracking(
    screens: list[ScreenBounds],
    initial: NativeWindowPrefs,
) -> None:
    current = NativeWindowPrefs(
        maximized=initial.maximized,
        width=initial.width,
        height=initial.height,
        x=initial.x,
        y=initial.y,
    )
    commit_task: asyncio.Task | None = None
    save_task: asyncio.Task | None = None
    pending_commit: NativeEventArguments | None = None

    def _apply_pending_commit_sync() -> None:
        nonlocal pending_commit
        if pending_commit is None or current.maximized:
            return
        event = pending_commit
        pending_commit = None
        if event.type == "resized":
            width, height = int(event.args["width"]), int(event.args["height"])
            if geometry_looks_maximized(width, height, screens):
                return
            current.width, current.height = width, height
        elif event.type == "moved":
            current.x, current.y = int(event.args["x"]), int(event.args["y"])

    def _schedule_geometry_commit(event: NativeEventArguments) -> None:
        nonlocal commit_task, pending_commit
        pending_commit = event
        if commit_task is not None:
            commit_task.cancel()

        async def _commit_after_settle() -> None:
            try:
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                return
            _apply_pending_commit_sync()

        commit_task = asyncio.create_task(_commit_after_settle())

    def _schedule_debounced_save() -> None:
        nonlocal save_task
        if save_task is not None:
            save_task.cancel()

        async def _wait_and_save() -> None:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                return
            save_native_window_prefs(current)

        save_task = asyncio.create_task(_wait_and_save())

    def _apply_native_event(event: NativeEventArguments) -> None:
        nonlocal commit_task
        if event.type == "maximized":
            current.maximized = True
            if commit_task is not None:
                commit_task.cancel()
                commit_task = None
        elif event.type == "restored":
            current.maximized = False
        elif event.type in ("resized", "moved"):
            _schedule_geometry_commit(event)
        _schedule_debounced_save()

    def _on_native_closed(_event: NativeEventArguments) -> None:
        nonlocal commit_task, save_task
        if commit_task is not None:
            commit_task.cancel()
            commit_task = None
        _apply_pending_commit_sync()
        if save_task is not None:
            save_task.cancel()
            save_task = None
        save_native_window_prefs(current)

    app.native.on("resized", _apply_native_event)
    app.native.on("moved", _apply_native_event)
    app.native.on("maximized", _apply_native_event)
    app.native.on("restored", _apply_native_event)
    app.native.on("closed", _on_native_closed)


# ── entry point ────────────────────────────────────────────────────────────


def run_gui(native: bool = False, host: str | None = None, *, allow_network: bool = False) -> None:
    """Launch the MyPySkinDose NiceGUI app.

    Binds to 127.0.0.1 (localhost only) by default. The GUI has no authentication
    and loads PHI-derived RDSR data into a single process-global, shared state, so
    it must not be exposed on the network unintentionally — and NiceGUI's browser
    mode would otherwise default to 0.0.0.0 (all interfaces). A non-loopback
    ``host`` also requires the explicit ``allow_network`` acknowledgement; only
    enable it on a trusted network and behind appropriate access controls.
    """
    configure_logging()
    dprint("GUI", f"Starting run_gui, native={native}")

    if native:

        @app.on_connect
        def _handle_native_focus():
            try:
                if app.native.main_window is not None:
                    set_on_top = getattr(app.native.main_window, "set_on_top", None)
                    if callable(set_on_top):
                        set_on_top(True)
            except Exception as exc:
                safe_error_event(logger, "native_window_focus", exc, level=logging.DEBUG)

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
        screens = _detect_native_screens()
        prefs = _resolve_native_window_prefs(screens)
        original_maximized = prefs.maximized
        prefs = _normalize_macos_maximized_startup(prefs, screens)
        app.native.window_args.update(
            width=prefs.width,
            height=prefs.height,
            x=prefs.x,
            y=prefs.y,
        )
        if prefs.maximized:
            app.native.window_args["maximized"] = True
        elif original_maximized and sys.platform == "darwin":
            save_native_window_prefs(prefs)
        window_size = (prefs.width, prefs.height)
        _register_native_geometry_tracking(screens, prefs)

    bind_host = host or "127.0.0.1"
    if bind_host not in ("127.0.0.1", "localhost"):
        if not allow_network:
            raise ValueError("network_gui_binding_requires_explicit_acknowledgement")
        logger.warning("non_loopback_gui_binding_requested")

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
