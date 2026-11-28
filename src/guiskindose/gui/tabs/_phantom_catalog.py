"""Phantom catalog status rows and pack install on the Settings tab."""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, Any

from nicegui import run, ui

from guiskindose import __version__
from guiskindose.gui.helpers import get_human_mesh_options, mesh_stem_is_installed
from guiskindose.gui.io_helpers import _is_native_mode, open_phantom_pack_stream
from guiskindose.gui.phantom_pack_download_controller import PhantomPackDownloadController
from guiskindose.gui.ui_copy import copy_text
from guiskindose.gui.window_prefs import show_demo_phantoms_enabled
from guiskindose.mesh_measurement_cache import clear_mesh_measurement_caches_for_stems
from guiskindose.phantom_library import (
    _WINDOWS_LIBRARY_UNAVAILABLE,
    PhantomLibraryUnavailableError,
    default_user_library_dir,
    missing_clinical_stems,
)
from guiskindose.phantom_mesh_names import (
    _CLINICAL_SORT_ORDER,
    _PREVIEW_REDUCED_SUFFIXES,
    DEMO_HUMAN_MESHES,
    GUI_HIDDEN_HUMAN_MESHES,
    human_mesh_display_label,
    package_phantom_data_dir,
)
from guiskindose.phantom_pack import PhantomPackError
from guiskindose.phantom_pack_cli import install_phantom_pack_from_stream
from guiskindose.phantom_pack_download import DOWNLOAD_UNAVAILABLE
from guiskindose.phantom_pack_install import InstallResult, default_install_library_dir
from guiskindose.phantom_pack_release import pack_release_url
from guiskindose.privacy import safe_error_event

logger = logging.getLogger(__name__)

_MAX_PACK_UPLOAD_BYTES = 80 * 1024 * 1024
_SPOOL_MAX_BYTES = 1024 * 1024


def _new_pack_spool() -> tempfile.SpooledTemporaryFile[bytes]:
    """Open the upload spool; called on a worker thread to keep file I/O off the event loop."""
    return tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)


def _catalog_stems(*, include_demos: bool) -> list[str]:
    stems = [
        stem
        for stem in _CLINICAL_SORT_ORDER
        if not any(stem.endswith(suffix) for suffix in _PREVIEW_REDUCED_SUFFIXES)
        and stem not in GUI_HIDDEN_HUMAN_MESHES
    ]
    if include_demos:
        stems.extend(sorted(DEMO_HUMAN_MESHES))
    return stems


def _notify_install_failure(status_label: Any) -> None:
    message = copy_text("settings.phantom_catalog.install_failure")
    status_label.set_text(message)
    ui.notify(message, type="negative", multi_line=True)


def _notify_phantom_pack_error(status_label: Any, exc: PhantomPackError) -> None:
    _notify_install_failure(status_label)
    ui.notify(exc.user_message(), type="negative", multi_line=True)


def _notify_library_unavailable(status_label: Any) -> None:
    _notify_install_failure(status_label)
    ui.notify(_WINDOWS_LIBRARY_UNAVAILABLE, type="negative", multi_line=True)


def _render_catalog_rows() -> None:
    for stem in _catalog_stems(include_demos=show_demo_phantoms_enabled()):
        label = human_mesh_display_label(stem)
        key = (
            "settings.phantom_catalog.status_installed"
            if mesh_stem_is_installed(stem)
            else "settings.phantom_catalog.status_missing"
        )
        ui.label(f"{label} — {copy_text(key)}").classes("text-caption")


@dataclass
class _PhantomCatalogSection:
    """Settings-tab catalog rows and pack install (browser upload or native dialog)."""

    mesh_select: Any
    on_change: Callable[[], None]
    status_label: Any = None
    _refresh_catalog_rows: Callable[..., Any] = field(default=lambda: None, repr=False)
    _refresh_actions: Callable[..., Any] = field(default=lambda: None, repr=False)
    _download_controller: PhantomPackDownloadController | None = field(default=None, repr=False)

    def refresh_mesh_options(self) -> None:
        self.mesh_select.options = get_human_mesh_options()
        self.mesh_select.update()
        self._refresh_catalog_rows()

    def report_install_success(self, result: InstallResult) -> None:
        """Show the install counts, drop cached measurements for the new meshes, and refresh the mesh list and rows."""
        assert self.status_label is not None
        clear_mesh_measurement_caches_for_stems(result.installed_stems)
        self.status_label.set_text(
            copy_text("settings.phantom_catalog.install_success").format(
                installed=result.installed,
                skipped=result.skipped_shipped,
            )
        )
        self.refresh_mesh_options()
        self._refresh_actions()
        self.on_change()

    async def commit_install(self, stream: IO[bytes]) -> None:
        """Install the pack from *stream* on a worker thread and report success or a fixed failure sentence. Always closes *stream*."""
        assert self.status_label is not None
        stream.seek(0)
        import guiskindose.phantom_pack_pin as pack_pin_module

        result: InstallResult
        try:
            result = await run.io_bound(
                install_phantom_pack_from_stream,
                stream,
                expected_manifest_sha256=pack_pin_module.EXPECTED_PHANTOM_PACK_SHA256,
                app_version=__version__,
                user_library_dir=None,
                shipped_dir=package_phantom_data_dir().resolve(),
            )
        except PhantomPackError as exc:
            _notify_phantom_pack_error(self.status_label, exc)
            return
        except PhantomLibraryUnavailableError:
            _notify_library_unavailable(self.status_label)
            return
        finally:
            stream.close()
        self.report_install_success(result)

    async def install_upload(self, event: Any) -> None:
        """Stream a browser upload into a spool under the size cap, then install it."""
        assert self.status_label is not None
        # NiceGUI has already buffered the upload; the server-side middleware caps that. This cap keeps the spool bounded.
        spool = await run.io_bound(_new_pack_spool)
        exceeded = False
        try:
            try:
                async for chunk in event.file.iterate():
                    if spool.tell() + len(chunk) > _MAX_PACK_UPLOAD_BYTES:
                        exceeded = True
                        break
                    await run.io_bound(spool.write, chunk)
            except Exception as exc:
                safe_error_event(logger, "phantom_pack_upload_read", exc)
                _notify_install_failure(self.status_label)
                return
            if exceeded:
                _notify_install_failure(self.status_label)
                return
            await self.commit_install(spool)
        finally:
            # Close synchronously: an awaited close would itself be cancelled during shutdown.
            if not spool.closed:
                spool.close()

    async def native_install(self) -> None:
        """Open a pack through the native file dialog and install it; a cancelled dialog does nothing."""
        assert self.status_label is not None
        try:
            stream = await open_phantom_pack_stream()
        except Exception as exc:
            safe_error_event(logger, "phantom_pack_open_dialog", exc)
            _notify_install_failure(self.status_label)
            return
        if stream is None:
            return  # the native dialog was cancelled; io_bound cancellation raises instead
        await self.commit_install(stream)

    def mount_install_control(self) -> None:
        if _is_native_mode():
            ui.button(
                copy_text("settings.phantom_catalog.install_button"),
                on_click=self.native_install,
            ).classes("q-mt-sm")
            return
        pack_upload = (
            ui.upload(
                label=copy_text("settings.phantom_catalog.install_button"),
                max_file_size=_MAX_PACK_UPLOAD_BYTES,
            )
            .props('accept=".zip" flat bordered color=primary auto-upload')
            .classes("uploader-no-list q-mt-sm")
        )
        pack_upload.on_upload(self.install_upload)

    def _missing_stems(self) -> list[str]:
        return missing_clinical_stems(
            shipped_dir=package_phantom_data_dir().resolve(),
            user_library_dir=default_user_library_dir(),
        )

    def mount_pack_actions(self) -> None:
        """Render download and local-install controls, or the catalog-complete caption."""
        if not self._missing_stems():
            ui.label(copy_text("settings.phantom_catalog.catalog_complete")).classes("text-caption text-grey-5")
            self._download_controller = None
            return
        ui.label(copy_text("settings.phantom_catalog.download_caption")).classes("text-caption text-grey-5")
        if pack_release_url(__version__) is None:
            with ui.row().classes("items-center q-gutter-sm"):
                ui.label(DOWNLOAD_UNAVAILABLE).classes("text-caption text-warning")
                self.mount_install_control()
            self._download_controller = None
            return
        self._mount_download_controls()

    def _mount_download_controls(self) -> None:
        try:
            library_dir = default_install_library_dir()
        except PhantomLibraryUnavailableError:
            with ui.row().classes("items-center q-gutter-sm"):
                ui.label(_WINDOWS_LIBRARY_UNAVAILABLE).classes("text-caption text-warning")
                self.mount_install_control()
            self._download_controller = None
            return
        with ui.row().classes("items-center q-gutter-sm"):
            button = ui.button(copy_text("settings.phantom_catalog.download_button"))
            self.mount_install_control()
        progress = ui.linear_progress(value=0.0, show_value=False).classes("w-full")
        progress.visible = False
        cancel = ui.button(copy_text("settings.phantom_catalog.download_cancel_button")).props("flat")
        cancel.visible = False
        import guiskindose.phantom_pack_pin as pack_pin_module

        controller = PhantomPackDownloadController(
            status_label=self.status_label,
            button=button,
            progress_bar=progress,
            cancel_button=cancel,
            on_installed=self.report_install_success,
            expected_manifest_sha256=pack_pin_module.EXPECTED_PHANTOM_PACK_SHA256,
            app_version=__version__,
            user_library_dir=library_dir,
            shipped_dir=package_phantom_data_dir().resolve(),
        )
        button.on_click(controller.start)
        cancel.on_click(controller.cancel)
        self._download_controller = controller


def build_phantom_catalog_section(
    *,
    mesh_select: Any,
    on_change: Callable[[], None],
) -> Callable[[], None]:
    """Render catalog status rows and pack install; return a mesh-options refresher."""
    section = _PhantomCatalogSection(mesh_select=mesh_select, on_change=on_change)
    section.status_label = ui.label("").classes("text-caption text-warning")

    @ui.refreshable
    def _catalog_rows() -> None:
        _render_catalog_rows()

    @ui.refreshable
    def _pack_actions() -> None:
        section.mount_pack_actions()

    section._refresh_catalog_rows = _catalog_rows.refresh
    section._refresh_actions = _pack_actions.refresh

    ui.label(copy_text("settings.phantom_catalog.section_title")).classes("text-subtitle2 q-mt-sm")
    _catalog_rows()
    _pack_actions()
    return section.refresh_mesh_options
