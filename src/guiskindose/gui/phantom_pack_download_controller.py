"""Progress, cancel, retry, and busy-guard orchestration for pack downloads.

The worker runs on ``run.io_bound``. NiceGUI 4 cancels the await but not the
thread, so ``DownloadControl.cancel`` closes the response to unblock a read.
The active-download record lives at module level and is cleared by the worker,
not the page handler, so a page reload cannot lose the guard while a cancelled
download is still draining.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nicegui import run, ui

from guiskindose.gui.ui_copy import copy_text
from guiskindose.phantom_pack import PhantomPackError
from guiskindose.phantom_pack_download import (
    DOWNLOAD_CANCELLED,
    DownloadControl,
    DownloadProgress,
    PhantomPackDownloadCancelled,
    download_release_pack,
)
from guiskindose.phantom_pack_install import InstallResult
from guiskindose.privacy import safe_error_event

logger = logging.getLogger(__name__)

_ACTIVE_LOCK = threading.Lock()
_ACTIVE: DownloadControl | None = None
_POLL_SECONDS = 0.2


def _claim_active(control: DownloadControl) -> bool:
    global _ACTIVE
    with _ACTIVE_LOCK:
        if _ACTIVE is not None:
            return False
        _ACTIVE = control
        return True


def _release_active(control: DownloadControl) -> None:
    global _ACTIVE
    with _ACTIVE_LOCK:
        if _ACTIVE is control:
            _ACTIVE = None


def download_is_active() -> bool:
    """True while a worker owns the process-level download guard (tests and UI)."""
    with _ACTIVE_LOCK:
        return _ACTIVE is not None


class PhantomPackDownloadController:
    """Drive one download control group: start, poll, cancel, retry."""

    def __init__(
        self,
        *,
        status_label: Any,
        button: Any,
        progress_bar: Any,
        cancel_button: Any,
        on_installed: Callable[[InstallResult], None],
        expected_manifest_sha256: str,
        app_version: str,
        user_library_dir: Path,
        shipped_dir: Path,
        timer_factory: Callable[..., Any] = ui.timer,
    ) -> None:
        self._status_label = status_label
        self._button = button
        self._progress_bar = progress_bar
        self._cancel_button = cancel_button
        self._on_installed = on_installed
        self._expected_manifest_sha256 = expected_manifest_sha256
        self._app_version = app_version
        self._user_library_dir = user_library_dir
        self._shipped_dir = shipped_dir
        self._timer_factory = timer_factory
        self._control: DownloadControl | None = None
        self._progress: DownloadProgress | None = None

    async def start(self) -> None:
        """Start a download, or report the busy sentence while another drains."""
        control = DownloadControl()
        if not _claim_active(control):
            self._status_label.set_text(copy_text("settings.phantom_catalog.download_busy"))
            ui.notify(copy_text("settings.phantom_catalog.download_busy"), type="warning")
            return
        progress = DownloadProgress()
        self._control = control
        self._progress = progress
        scheduled = False
        timer: Any = None
        try:
            self._set_running()
            timer = self._timer_factory(_POLL_SECONDS, self._poll)
            # From here the worker owns the guard. ``shield`` keeps the worker task
            # alive when the page handler is cancelled, and the worker's ``finally``
            # is the only release. Setup failures before this line release below.
            worker = asyncio.create_task(run.io_bound(self._worker, control, progress))
            scheduled = True
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            control.cancel()
            self._status_label.set_text(copy_text("settings.phantom_catalog.download_cancelling"))
            raise
        except PhantomPackDownloadCancelled:
            self._finish_error(DOWNLOAD_CANCELLED, negative=False)
        except PhantomPackError as exc:
            self._finish_error(exc.user_message())
        except Exception as exc:
            safe_error_event(logger, "phantom_pack_download", exc)
            self._finish_error(copy_text("settings.phantom_catalog.install_failure"))
        else:
            self._finish_success(result)
        finally:
            if timer is not None:
                timer.cancel()
            if not scheduled:
                _release_active(control)
            self._control = None
            self._progress = None

    def _worker(self, control: DownloadControl, progress: DownloadProgress) -> InstallResult:
        try:
            return download_release_pack(
                expected_manifest_sha256=self._expected_manifest_sha256,
                app_version=self._app_version,
                user_library_dir=self._user_library_dir,
                shipped_dir=self._shipped_dir,
                control=control,
                progress=progress,
            )
        finally:
            _release_active(control)

    def cancel(self) -> None:
        """Request cancellation; the worker closes its response to unblock a read."""
        if self._control is None:
            return
        self._control.cancel()
        self._cancel_button.disable()
        self._status_label.set_text(copy_text("settings.phantom_catalog.download_cancelling"))

    def _poll(self) -> None:
        if self._progress is None:
            return
        received, total, phase = self._progress.snapshot()
        if phase == "installing":
            self._progress_bar.set_value(1.0)
            return
        if total:
            fraction = min(1.0, received / total)
            percent = int(fraction * 100)
            self._progress_bar.set_value(fraction)
            self._status_label.set_text(
                copy_text("settings.phantom_catalog.download_progress").format(percent=percent)
            )
            return
        self._status_label.set_text(copy_text("settings.phantom_catalog.download_progress_unknown"))

    def _set_running(self) -> None:
        self._button.disable()
        self._button.set_text(copy_text("settings.phantom_catalog.download_button"))
        self._cancel_button.enable()
        self._cancel_button.visible = True
        self._progress_bar.visible = True
        self._progress_bar.set_value(0.0)
        self._status_label.set_text(copy_text("settings.phantom_catalog.download_progress_unknown"))

    def _finish_success(self, result: InstallResult) -> None:
        self._progress_bar.visible = False
        self._cancel_button.visible = False
        self._button.enable()
        self._on_installed(result)

    def _finish_error(self, message: str, *, negative: bool = True) -> None:
        self._progress_bar.visible = False
        self._cancel_button.visible = False
        self._button.enable()
        self._button.set_text(copy_text("settings.phantom_catalog.download_retry_button"))
        self._status_label.set_text(message)
        ui.notify(message, type="negative" if negative else "warning", multi_line=True)
