"""Unit tests for ``guiskindose.export.png_browser``. None of them launch a browser."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import pytest

from guiskindose.edition import PngExportUnavailableError
from guiskindose.export import MissingExportDependencyError, png_browser
from guiskindose.export.png_browser import (
    BUNDLED_BROWSER_MESSAGE,
    PNG_BROWSER_MESSAGE,
    PNG_RENDER_MESSAGE,
    BundledBrowserUnavailableError,
    PngBrowserUnavailableError,
    PngRenderError,
    bundled_browser,
    bundled_browser_for_render,
    figure_to_png,
    resolve_image_options,
)

importlib.import_module("plotly.io._kaleido")  # bind the real kaleido now; tests below fake it in sys.modules


class _FakeFig:
    def __init__(self, layout: dict[str, Any] | None = None) -> None:
        self.layout = layout or {}
        self.to_image_calls: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {"data": [], "layout": self.layout}

    def to_image(self, **kwargs: Any) -> bytes:
        self.to_image_calls.append(kwargs)
        return b"pip"


@pytest.fixture
def kaleido_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"calc": [], "server": []}
    fake = types.ModuleType("kaleido")

    async def calc_fig(*args: Any, **kwargs: Any) -> bytes:
        calls["calc"].append((args, kwargs))
        return b"png"

    async def calc_fig_sync(*args: Any, **kwargs: Any) -> bytes:  # must never be used
        raise AssertionError("calc_fig_sync routes to a running global server and drops kopts")

    def start_sync_server(*args: Any, **kwargs: Any) -> None:
        calls["server"].append((args, kwargs))

    fake.calc_fig = calc_fig  # type: ignore[attr-defined]
    fake.calc_fig_sync = calc_fig_sync  # type: ignore[attr-defined]
    fake.start_sync_server = start_sync_server  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kaleido", fake)
    return calls


def _bundled_chrome_path(exe_parent: Path, platform: str) -> Path:
    if platform == "win32":
        return exe_parent / "chromium" / "chrome.exe"
    if platform == "darwin":
        return exe_parent.parent / "Helpers" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    return exe_parent / "chromium" / "chrome"


def _frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, platform: str, *, browser: bool) -> Path:
    if platform == "darwin":
        exe_parent = tmp_path / "Contents" / "MacOS"
        exe_parent.mkdir(parents=True)
        exe = exe_parent / "GUISkinDose"
    else:
        exe = tmp_path / ("GUISkinDose.exe" if platform == "win32" else "GUISkinDose")
        exe_parent = tmp_path
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(png_browser, "_host_platform", lambda: platform)
    monkeypatch.setattr(png_browser, "png_export_available", lambda: True)
    chrome = _bundled_chrome_path(exe_parent, platform)
    if browser:
        chrome.parent.mkdir(parents=True, exist_ok=True)
        chrome.write_bytes(b"x")
    return chrome


def test_not_frozen_uses_to_image_and_never_kaleido(monkeypatch, kaleido_calls) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(png_browser, "png_export_available", lambda: True)
    fig = _FakeFig()
    assert figure_to_png(fig, width=10, scale=2) == b"pip"
    assert fig.to_image_calls == [{"format": "png", "width": 10, "height": None, "scale": 2}]
    assert kaleido_calls["calc"] == []
    assert kaleido_calls["server"] == []


class _RaisingFig:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def to_image(self, **_kwargs: Any) -> bytes:
        raise self.exc


def _source_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(png_browser, "png_export_available", lambda: True)


def test_source_missing_kaleido_becomes_missing_dependency(monkeypatch) -> None:
    _source_install(monkeypatch)
    monkeypatch.setattr(png_browser, "missing_backend", lambda _fmt: "kaleido")
    fig = _RaisingFig(ValueError("raw kaleido detail"))

    with pytest.raises(MissingExportDependencyError) as excinfo:
        figure_to_png(fig)

    exc = excinfo.value
    assert exc.format == "png"
    assert exc.package == "kaleido"
    assert "pip install kaleido" in exc.install_hint
    assert "raw kaleido detail" not in str(exc)


def test_source_missing_browser_is_typed(monkeypatch) -> None:
    _source_install(monkeypatch)
    monkeypatch.setattr(png_browser, "missing_backend", lambda _fmt: None)
    monkeypatch.setattr(png_browser, "system_browser_available", lambda: False)
    fig = _RaisingFig(RuntimeError("Chrome not found"))

    with pytest.raises(PngBrowserUnavailableError) as excinfo:
        figure_to_png(fig)

    assert str(excinfo.value) == PNG_BROWSER_MESSAGE
    assert "Chrome not found" not in str(excinfo.value)


@pytest.mark.parametrize("probe", [True, None])
def test_source_other_render_failure_stays_generic(monkeypatch, probe) -> None:
    _source_install(monkeypatch)
    monkeypatch.setattr(png_browser, "missing_backend", lambda _fmt: None)
    monkeypatch.setattr(png_browser, "system_browser_available", lambda: probe)
    fig = _RaisingFig(ValueError("bad figure"))

    with pytest.raises(PngRenderError) as excinfo:
        figure_to_png(fig)

    assert str(excinfo.value) == PNG_RENDER_MESSAGE
    assert "bad figure" not in str(excinfo.value)


def test_browser_probe_never_downloads_or_touches_network(monkeypatch) -> None:
    import socket
    import urllib.request

    _cli_utils = pytest.importorskip("choreographer.cli._cli_utils")
    calls: list[str] = []

    def _record(name):
        def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
            calls.append(name)
            raise AssertionError(f"the failure probe must not call {name}")

        return _forbidden

    # Every choreographer/urllib download or connection entry point the probe could reach.
    monkeypatch.setattr(urllib.request, "urlopen", _record("urlopen"))
    monkeypatch.setattr(socket, "create_connection", _record("create_connection"))
    monkeypatch.setattr(_cli_utils, "get_chrome_sync", _record("get_chrome_sync"))
    monkeypatch.setattr(_cli_utils, "get_chrome", _record("get_chrome"))

    # ``system_browser_available`` swallows probe errors, so the call counts (not
    # the return value) are what prove no download/network path ran.
    assert png_browser.system_browser_available() in (True, False, None)
    assert calls == []


def test_frozen_windows_passes_bundled_path(monkeypatch, tmp_path, kaleido_calls) -> None:
    chrome = _frozen(monkeypatch, tmp_path, "win32", browser=True)
    assert figure_to_png(_FakeFig(), width=800, height=600, scale=1.5) == b"png"
    ((_args, kwargs),) = kaleido_calls["calc"]
    assert Path(kwargs["kopts"]["path"]) == chrome
    assert kwargs["kopts"]["mathjax"] is False
    assert kwargs["opts"]["width"] == 800
    assert kwargs["opts"]["scale"] == 1.5
    assert kaleido_calls["server"] == []


def test_plotlyjs_passed_only_when_set(monkeypatch, tmp_path, kaleido_calls) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=True)
    monkeypatch.setattr(pio.defaults, "plotlyjs", None)
    figure_to_png(_FakeFig())
    assert "plotlyjs" not in kaleido_calls["calc"][-1][1]["kopts"]
    monkeypatch.setattr(pio.defaults, "plotlyjs", "https://example.invalid/plotly.js")
    figure_to_png(_FakeFig())
    assert kaleido_calls["calc"][-1][1]["kopts"]["plotlyjs"] == "https://example.invalid/plotly.js"


def test_frozen_browser_missing_fails_closed(monkeypatch, tmp_path, kaleido_calls) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=False)
    fig = _FakeFig()
    with pytest.raises(BundledBrowserUnavailableError) as info:
        figure_to_png(fig)
    assert str(info.value) == BUNDLED_BROWSER_MESSAGE
    assert kaleido_calls["calc"] == []


def test_non_browser_error_becomes_generic_render_error_and_is_scrubbed(monkeypatch, tmp_path, kaleido_calls) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=True)

    async def boom(*_a: Any, **_k: Any) -> bytes:
        raise ValueError(f"bad figure {tmp_path}")

    monkeypatch.setattr(sys.modules["kaleido"], "calc_fig", boom)
    fig = _FakeFig()
    with pytest.raises(PngRenderError) as info:
        figure_to_png(fig)
    assert str(info.value) == PNG_RENDER_MESSAGE
    assert str(tmp_path) not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__
    assert not isinstance(info.value, BundledBrowserUnavailableError)


@pytest.mark.parametrize(
    "failure", ["ChromeNotFoundError", "BrowserFailedError", "BrowserClosedError", "OSError", "TimeoutError"]
)
def test_browser_launch_failure_is_unavailable_and_scrubbed(monkeypatch, tmp_path, kaleido_calls, failure) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=True)
    exc_type = {"OSError": OSError, "TimeoutError": TimeoutError}.get(failure) or type(failure, (RuntimeError,), {})

    async def boom(*_a: Any, **_k: Any) -> bytes:
        raise exc_type(f"cannot start {tmp_path}")

    monkeypatch.setattr(sys.modules["kaleido"], "calc_fig", boom)
    fig = _FakeFig()
    with pytest.raises(BundledBrowserUnavailableError) as info:
        figure_to_png(fig)
    assert str(tmp_path) not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


def test_render_thread_timeout_is_unavailable(monkeypatch, tmp_path, kaleido_calls) -> None:
    import asyncio
    import threading

    _frozen(monkeypatch, tmp_path, "win32", browser=True)
    monkeypatch.setattr(png_browser, "_RENDER_TIMEOUT_S", 0.05)
    release = threading.Event()

    async def hang(*_a: Any, **_k: Any) -> bytes:
        while not release.is_set():
            await asyncio.sleep(0.01)
        return b""

    monkeypatch.setattr(sys.modules["kaleido"], "calc_fig", hang)
    fig = _FakeFig()
    try:
        with pytest.raises(BundledBrowserUnavailableError):
            figure_to_png(fig)
    finally:
        release.set()


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_frozen_unix_passes_bundled_path(monkeypatch, tmp_path, kaleido_calls, platform) -> None:
    chrome = _frozen(monkeypatch, tmp_path, platform, browser=True)
    assert bundled_browser_for_render() == chrome.resolve()
    assert figure_to_png(_FakeFig(), width=800, height=600, scale=1.5) == b"png"
    ((_args, kwargs),) = kaleido_calls["calc"]
    assert Path(kwargs["kopts"]["path"]) == chrome
    assert kwargs["kopts"]["mathjax"] is False
    assert kwargs["opts"]["width"] == 800
    assert kwargs["opts"]["scale"] == 1.5
    assert kaleido_calls["server"] == []


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_frozen_unix_browser_missing_fails_closed(monkeypatch, tmp_path, kaleido_calls, platform) -> None:
    _frozen(monkeypatch, tmp_path, platform, browser=False)
    fig = _FakeFig()
    with pytest.raises(BundledBrowserUnavailableError) as info:
        figure_to_png(fig)
    assert str(info.value) == BUNDLED_BROWSER_MESSAGE
    assert kaleido_calls["calc"] == []


def test_bundled_browser_honors_base_and_platform(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(png_browser, "_host_platform", lambda: "win32")
    assert bundled_browser(tmp_path) == tmp_path / "chromium" / "chrome.exe"
    monkeypatch.setattr(png_browser, "_host_platform", lambda: "linux")
    assert bundled_browser(tmp_path) == tmp_path / "chromium" / "chrome"
    macos = tmp_path / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    monkeypatch.setattr(png_browser, "_host_platform", lambda: "darwin")
    assert bundled_browser(macos) == (
        tmp_path / "Contents" / "Helpers" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
    )
    monkeypatch.setattr(png_browser, "_host_platform", lambda: "darwin")
    assert bundled_browser(tmp_path) == tmp_path / "chromium" / "chrome"


def test_not_frozen_has_no_render_browser(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(png_browser, "_host_platform", lambda: "win32")
    assert bundled_browser_for_render() is None


@pytest.mark.parametrize("frozen", [False, True])
def test_light_raises_before_kaleido(monkeypatch, tmp_path, frozen) -> None:
    monkeypatch.setitem(sys.modules, "kaleido", None)  # any import would raise ImportError
    if frozen:
        _frozen(monkeypatch, tmp_path, "win32", browser=True)
    monkeypatch.setattr(png_browser, "png_export_available", lambda: False)
    fig = _FakeFig()
    with pytest.raises(PngExportUnavailableError):
        figure_to_png(fig)


def test_resolve_matches_plotly_order() -> None:
    d = pio.defaults
    assert resolve_image_options({}, None, None, None, d) == {
        "format": "png",
        "width": d.default_width,
        "height": d.default_height,
        "scale": d.default_scale,
    }
    layout = {"width": 500, "template": {"layout": {"width": 400, "height": 300}}}
    got = resolve_image_options({"layout": layout}, None, None, None, d)
    assert (got["width"], got["height"]) == (500, 300)
    got = resolve_image_options({"layout": layout}, 900, 700, 3, d)
    assert (got["width"], got["height"], got["scale"]) == (900, 700, 3)


def test_resolve_matches_plotly_to_image(monkeypatch) -> None:
    """The frozen path asks Kaleido for the same size and scale ``fig.to_image`` would."""
    seen: dict[str, Any] = {}
    fake = types.ModuleType("kaleido")

    def calc_fig_sync(fig_dict: Any, opts: Any = None, **_k: Any) -> bytes:
        seen.update(opts)
        return b""

    fake.calc_fig_sync = calc_fig_sync  # type: ignore[attr-defined]
    errors = types.ModuleType("kaleido.errors")
    errors.ChromeNotFoundError = type("ChromeNotFoundError", (Exception,), {})  # type: ignore[attr-defined]
    fake.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kaleido", fake)
    monkeypatch.setitem(sys.modules, "kaleido.errors", errors)
    monkeypatch.setattr("plotly.io._kaleido.kaleido_available", lambda: True)
    monkeypatch.setattr("plotly.io._kaleido.kaleido", fake, raising=False)
    fig = go.Figure(layout={"width": 640})
    fig.to_image(format="png")
    expected = dict(seen)
    resolved = resolve_image_options(fig.to_dict(), None, None, None, pio.defaults)
    assert resolved == expected


def test_runs_inside_a_running_event_loop_and_ignores_global_server(monkeypatch, tmp_path, kaleido_calls) -> None:
    import asyncio

    chrome = _frozen(monkeypatch, tmp_path, "win32", browser=True)
    monkeypatch.setattr(
        sys.modules["kaleido"], "is_running", lambda: True, raising=False
    )  # a "running" global server must not matter

    async def caller() -> bytes:
        return figure_to_png(_FakeFig())

    assert asyncio.run(caller()) == b"png"
    ((_args, kwargs),) = kaleido_calls["calc"]
    assert Path(kwargs["kopts"]["path"]) == chrome


@pytest.mark.parametrize("template", [None, "plotly", {"layout": None}])
def test_resolve_tolerates_odd_template(template) -> None:
    d = pio.defaults
    got = resolve_image_options({"layout": {"template": template}}, None, None, None, d)
    assert (got["width"], got["height"]) == (d.default_width, d.default_height)
    assert resolve_image_options({"layout": None}, None, None, None, d)["width"] == d.default_width


def test_bad_figure_becomes_unavailable_error(monkeypatch, tmp_path, kaleido_calls) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=True)

    class Bad(_FakeFig):
        def to_dict(self) -> dict[str, Any]:
            raise ValueError(str(tmp_path))

    bad = Bad()
    with pytest.raises(PngRenderError) as info:
        figure_to_png(bad)
    assert str(tmp_path) not in str(info.value)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_worker_dying_without_a_result_does_not_hang(monkeypatch, tmp_path, kaleido_calls) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=True)

    async def die(*_a: Any, **_k: Any) -> bytes:
        raise SystemExit  # not an Exception: the worker cannot report it

    monkeypatch.setattr(sys.modules["kaleido"], "calc_fig", die)
    fig = _FakeFig()
    with pytest.raises(PngRenderError):
        figure_to_png(fig)


@pytest.mark.parametrize("error", [BundledBrowserUnavailableError, PngRenderError])
def test_render_dosemap_png_returns_none_on_png_errors(monkeypatch, error) -> None:
    from guiskindose.export import images

    def _unavailable(*_a: Any, **_k: Any) -> bytes:
        raise error()

    monkeypatch.setattr(images, "png_export_available", lambda: True)
    monkeypatch.setattr(images, "figure_to_png", _unavailable)
    triangle = {
        "patient_skin_cells": {"x": [0.0, 1.0, 0.0], "y": [0.0, 0.0, 1.0], "z": [0.0, 0.0, 0.0]},
        "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
    }
    assert images.render_dosemap_png(np.zeros(3), triangle) is None


def test_render_failure_is_logged_by_class_only(monkeypatch, tmp_path, kaleido_calls) -> None:
    _frozen(monkeypatch, tmp_path, "win32", browser=True)
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        png_browser, "safe_error_event", lambda _logger, code, exc: events.append((code, type(exc).__name__))
    )

    async def boom(*_a: Any, **_k: Any) -> bytes:
        raise ValueError(f"bad figure {tmp_path}")

    monkeypatch.setattr(sys.modules["kaleido"], "calc_fig", boom)
    fig = _FakeFig()
    with pytest.raises(PngRenderError):
        figure_to_png(fig)
    assert events == [("bundled_browser_png_render", "ValueError")]


def test_browser_probe_uses_the_resolver_the_choreographer_floor_provides() -> None:
    """``Chromium.find_browser`` (choreographer >= 1.3.0, the declared floor) takes ``skip_local``."""
    import inspect

    from choreographer.browsers.chromium import Chromium

    assert "skip_local" in inspect.signature(Chromium.find_browser).parameters


@pytest.mark.parametrize(("resolved", "expected"), [("/opt/chrome", True), (None, False)])
def test_browser_probe_maps_the_resolver_result(
    monkeypatch: pytest.MonkeyPatch, resolved: str | None, expected: bool
) -> None:
    from choreographer.browsers.chromium import Chromium

    monkeypatch.setattr(Chromium, "find_browser", classmethod(lambda cls, **_kw: resolved))
    assert png_browser.system_browser_available() is expected


def test_browser_probe_is_uncertain_when_the_resolver_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from choreographer.browsers.chromium import Chromium

    monkeypatch.delattr(Chromium, "find_browser")
    assert png_browser.system_browser_available() is None
