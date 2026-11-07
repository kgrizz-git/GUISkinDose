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
from guiskindose.gui.ui_copy import copy_text
from guiskindose.gui.window_prefs import show_demo_phantoms_enabled
from guiskindose.mesh_measurement_cache import clear_mesh_measurement_caches_for_stems
from guiskindose.phantom_library import (
    _WINDOWS_LIBRARY_UNAVAILABLE,
    PhantomLibraryUnavailableError,
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
from guiskindose.phantom_pack_install import InstallResult
from guiskindose.privacy import safe_error_event

logger = logging.getLogger(__name__)

_MAX_PACK_UPLOAD_BYTES = 80 * 1024 * 1024
_SPOOL_MAX_BYTES = 1024 * 1024


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

    def refresh_mesh_options(self) -> None:
        self.mesh_select.options = get_human_mesh_options()
        self.mesh_select.update()
        self._refresh_catalog_rows()

    def report_install_success(self, result: InstallResult) -> None:
        assert self.status_label is not None
        clear_mesh_measurement_caches_for_stems(result.installed_stems)
        self.status_label.set_text(
            copy_text("settings.phantom_catalog.install_success").format(
                installed=result.installed,
                skipped=result.skipped_shipped,
            )
        )
        self.refresh_mesh_options()
        self.on_change()

    async def commit_install(self, stream: IO[bytes]) -> None:
        assert self.status_label is not None
        stream.seek(0)
        import guiskindose.phantom_pack_pin as pack_pin_module

        result: InstallResult | None = None
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
        if result is not None:
            self.report_install_success(result)

    async def install_upload(self, event: Any) -> None:
        assert self.status_label is not None
        spool: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)  # noqa: SIM115
        total = 0
        try:
            async for chunk in event.file.iterate():
                total += len(chunk)
                if total > _MAX_PACK_UPLOAD_BYTES:
                    spool.close()
                    _notify_install_failure(self.status_label)
                    return
                spool.write(chunk)
        except Exception as exc:
            safe_error_event(logger, "phantom_pack_upload_read", exc)
            spool.close()
            _notify_install_failure(self.status_label)
            return
        await self.commit_install(spool)

    async def native_install(self) -> None:
        assert self.status_label is not None
        try:
            stream = await open_phantom_pack_stream()
        except Exception as exc:
            safe_error_event(logger, "phantom_pack_open_dialog", exc)
            _notify_install_failure(self.status_label)
            return
        if stream is None:
            return
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

    section._refresh_catalog_rows = _catalog_rows.refresh

    ui.label(copy_text("settings.phantom_catalog.section_title")).classes("text-subtitle2 q-mt-sm")
    _catalog_rows()
    ui.label(copy_text("settings.phantom_catalog.phase3_caption")).classes("text-caption text-grey-5")
    section.mount_install_control()
    return section.refresh_mesh_options
