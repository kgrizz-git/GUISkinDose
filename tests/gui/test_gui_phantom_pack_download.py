"""Settings phantom-pack download controller and catalog action states."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui.phantom_pack_download_controller import (
    PhantomPackDownloadController,
    _claim_active,
    _release_active,
    download_is_active,
)
from guiskindose.phantom_pack_download import DOWNLOAD_CANCELLED, DownloadControl
from guiskindose.phantom_pack_install import InstallResult

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


class _Widget:
    def __init__(self) -> None:
        self.text = ""
        self.visible = True
        self.enabled = True
        self.value = 0.0

    def set_text(self, text: str) -> None:
        self.text = text

    def disable(self) -> None:
        self.enabled = False

    def enable(self) -> None:
        self.enabled = True

    def set_value(self, value: float) -> None:
        self.value = value


class _Timer:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


def _controller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installed: list[InstallResult]) -> tuple[
    PhantomPackDownloadController, _Widget, _Widget, _Widget, list[str], _Timer
]:
    from guiskindose.gui import phantom_pack_download_controller as module

    status = _Widget()
    button = _Widget()
    progress = _Widget()
    cancel = _Widget()
    notes: list[str] = []
    timer = _Timer()
    monkeypatch.setattr(module.ui, "notify", lambda message, **_k: notes.append(str(message)))
    controller = PhantomPackDownloadController(
        status_label=status,
        button=button,
        progress_bar=progress,
        cancel_button=cancel,
        on_installed=installed.append,
        expected_manifest_sha256="0" * 64,
        app_version="1.1.1",
        user_library_dir=tmp_path / "library",
        shipped_dir=tmp_path / "shipped",
        timer_factory=lambda *_a, **_k: timer,
    )
    return controller, status, button, progress, notes, timer


@pytest.mark.asyncio
async def test_start_installs_and_releases_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.gui import phantom_pack_download_controller as module

    installed: list[InstallResult] = []
    controller, _status, button, progress, _notes, timer = _controller(monkeypatch, tmp_path, installed)

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(module.run, "io_bound", _io_bound)
    monkeypatch.setattr(
        module,
        "download_release_pack",
        lambda **_kwargs: InstallResult(1, 0, ("senior_male",)),
    )
    await controller.start()
    assert installed
    assert installed[0].installed == 1
    assert download_is_active() is False
    assert timer.cancelled is True
    assert progress.visible is False
    assert button.enabled is True


@pytest.mark.asyncio
async def test_busy_guard_survives_a_second_controller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.gui import phantom_pack_download_controller as module

    installed: list[InstallResult] = []
    first, _status, _button, _progress, _notes, _timer = _controller(monkeypatch, tmp_path, installed)
    monkeypatch.setattr(
        module,
        "download_release_pack",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not start")),
    )
    control = DownloadControl()
    assert _claim_active(control)
    try:
        await first.start()
    finally:
        _release_active(control)
    assert "still finishing" in first._status_label.text  # type: ignore[attr-defined]
    assert download_is_active() is False


@pytest.mark.asyncio
async def test_cancelled_worker_shows_cancel_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.gui import phantom_pack_download_controller as module
    from guiskindose.phantom_pack_download import PhantomPackDownloadCancelled

    installed: list[InstallResult] = []
    controller, status, button, _progress, notes, _timer = _controller(monkeypatch, tmp_path, installed)

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def _cancel(**_kwargs):
        raise PhantomPackDownloadCancelled(DOWNLOAD_CANCELLED)

    monkeypatch.setattr(module.run, "io_bound", _io_bound)
    monkeypatch.setattr(module, "download_release_pack", _cancel)
    await controller.start()
    assert status.text == DOWNLOAD_CANCELLED
    assert button.text == "Retry download"
    assert notes
    assert notes[-1] == DOWNLOAD_CANCELLED


def test_cancel_requests_control_cancellation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    installed: list[InstallResult] = []
    controller, status, _button, _progress, _notes, _timer = _controller(monkeypatch, tmp_path, installed)
    control = DownloadControl()
    controller._control = control  # type: ignore[attr-defined]
    controller.cancel()
    assert control.cancelled is True
    assert "Cancelling" in status.text


def test_catalog_complete_hides_both_actions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_mesh_names import _CLINICAL_SORT_ORDER, _PREVIEW_REDUCED_SUFFIXES

    shipped = tmp_path / "shipped"
    shipped.mkdir()
    for stem in _CLINICAL_SORT_ORDER:
        if any(stem.endswith(suffix) for suffix in _PREVIEW_REDUCED_SUFFIXES):
            continue
        (shipped / f"{stem}.stl").write_bytes(b"solid t\nendsolid t\n")
    monkeypatch.setattr(catalog, "package_phantom_data_dir", lambda: shipped)
    monkeypatch.setattr(catalog, "default_user_library_dir", lambda: tmp_path / "library")

    section = catalog._PhantomCatalogSection(
        mesh_select=type("S", (), {"options": {}, "update": lambda self: None})(),
        on_change=lambda: None,
    )
    labels: list[str] = []
    install_calls: list[bool] = []

    class _Label:
        def classes(self, *_args, **_kwargs):
            return self

    def _label(text: str):
        labels.append(text)
        return _Label()

    monkeypatch.setattr(catalog.ui, "label", _label)
    monkeypatch.setattr(section, "mount_install_control", lambda: install_calls.append(True))
    section.mount_pack_actions()
    assert catalog.copy_text("settings.phantom_catalog.catalog_complete") in labels
    assert install_calls == []
    assert section._download_controller is None


def test_building_pack_actions_does_not_touch_the_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import socket

    from guiskindose.gui.tabs import _phantom_catalog as catalog
    from guiskindose.phantom_mesh_names import _CLINICAL_SORT_ORDER, _PREVIEW_REDUCED_SUFFIXES

    shipped = tmp_path / "shipped"
    shipped.mkdir()
    for stem in _CLINICAL_SORT_ORDER:
        if any(stem.endswith(suffix) for suffix in _PREVIEW_REDUCED_SUFFIXES):
            continue
        (shipped / f"{stem}.stl").write_bytes(b"solid t\nendsolid t\n")
    monkeypatch.setattr(catalog, "package_phantom_data_dir", lambda: shipped)
    monkeypatch.setattr(catalog, "default_user_library_dir", lambda: tmp_path / "library")

    def _no_socket(*_args, **_kwargs):
        raise AssertionError("no network at startup")

    monkeypatch.setattr(socket, "socket", _no_socket)
    section = catalog._PhantomCatalogSection(
        mesh_select=type("S", (), {"options": {}, "update": lambda self: None})(),
        on_change=lambda: None,
    )

    class _Label:
        def classes(self, *_args, **_kwargs):
            return self

    monkeypatch.setattr(catalog.ui, "label", lambda *_a, **_k: _Label())
    section.mount_pack_actions()


@pytest.mark.asyncio
async def test_setup_failure_releases_busy_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose.gui import phantom_pack_download_controller as module

    installed: list[InstallResult] = []
    controller, status, _button, _progress, _notes, _timer = _controller(monkeypatch, tmp_path, installed)

    def _bad_timer(*_args, **_kwargs):
        raise RuntimeError("timer setup failed")

    monkeypatch.setattr(controller, "_timer_factory", _bad_timer)
    await controller.start()
    assert download_is_active() is False

    async def _io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(module.run, "io_bound", _io_bound)
    monkeypatch.setattr(
        module,
        "download_release_pack",
        lambda **_kwargs: InstallResult(1, 0, ("senior_male",)),
    )
    controller._timer_factory = lambda *_a, **_k: _Timer()
    await controller.start()
    assert installed
    assert installed[-1].installed == 1
    assert "still finishing" not in status.text
    assert download_is_active() is False


@pytest.mark.asyncio
async def test_cancel_before_worker_starts_keeps_guard_until_worker_finishes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import asyncio
    import threading

    from guiskindose.gui import phantom_pack_download_controller as module
    installed: list[InstallResult] = []
    controller, _status, _button, _progress, _notes, _timer = _controller(monkeypatch, tmp_path, installed)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def _blocked_download(**_kwargs):
        started.set()
        try:
            release.wait(5)
            return InstallResult(0, 0)
        finally:
            finished.set()

    async def _schedule_then_cancel(fn, *args, **kwargs):
        del kwargs
        threading.Thread(target=fn, args=args, daemon=True).start()
        await asyncio.sleep(0)
        raise asyncio.CancelledError

    monkeypatch.setattr(module, "download_release_pack", _blocked_download)
    monkeypatch.setattr(module.run, "io_bound", _schedule_then_cancel)
    with pytest.raises(asyncio.CancelledError):
        await controller.start()
    assert started.wait(2)
    assert download_is_active() is True
    release.set()
    assert finished.wait(2)
    for _ in range(50):
        if not download_is_active():
            break
        await asyncio.sleep(0.01)
    assert download_is_active() is False
