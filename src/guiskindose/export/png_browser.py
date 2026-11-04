"""PNG rendering through the Chromium bundled in the frozen Full app.

``dev-docs/plans/archive/PORTABLE_PNG_BUNDLED_BROWSER_PLAN.md``. Plain ``fig.to_image()`` lets choreographer pick a
browser (a downloaded Chrome for Testing, then ``BROWSER_PATH``, then a system install).
In the frozen Full app that would ignore the Chromium shipped under ``<onedir>/chromium/``.
:func:`figure_to_png` therefore passes the bundled path to Kaleido explicitly.

It deliberately does not call ``kaleido.calc_fig_sync``. When Kaleido's global sync server is running
(someone called ``start_sync_server``), ``calc_fig_sync`` routes to it and drops ``kopts``, so the
bundled path would be silently ignored. Instead it runs the public async ``kaleido.calc_fig`` with
``asyncio.run`` on a fresh thread, the way Kaleido's own one-shot path does. Each call starts its own
browser and closes it, never touches the global server, and works when the caller already has a
running event loop. It never starts or stops a global server.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from guiskindose.edition import PngExportUnavailableError, png_export_available

BROWSER_DIR = "chromium"

BUNDLED_BROWSER_MESSAGE = (
    "The bundled browser for PNG export is missing or could not start in this GUISkinDose Full copy. "
    "Re-extract the download and try again."
)


class BundledBrowserUnavailableError(RuntimeError):
    """The frozen Full app cannot render PNG with its bundled browser."""

    def __init__(self) -> None:
        super().__init__(BUNDLED_BROWSER_MESSAGE)


def bundled_browser(base: Path | None = None) -> Path:
    """Path of the bundled Chromium: ``<base>/chromium/chrome[.exe]``; *base* defaults to the exe dir."""
    root = base if base is not None else Path(sys.executable).resolve().parent
    name = "chrome.exe" if sys.platform == "win32" else "chrome"
    return root / BROWSER_DIR / name


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundled_browser_for_render() -> Path | None:
    """The browser to hand to Kaleido, or ``None`` when none may be used.

    ``None`` when not frozen. On Windows, the bundled Chromium. On macOS and Linux also
    ``None``: choreographer launches Chromium there through
    ``[sys.executable, _unix_pipe_chromium_wrapper.py, ...]``, and in a frozen app
    ``sys.executable`` is the PyInstaller bootloader (PORTABLE_APP_PLAN.md, "Freeze").
    Until that wrapper item lands, frozen macOS and Linux Full builds fail PNG closed.
    """
    if not _is_frozen() or sys.platform != "win32":
        return None
    return bundled_browser()


def _layout_size(fig_dict: dict[str, Any], key: str) -> Any:
    layout = fig_dict.get("layout")
    if not isinstance(layout, dict):
        return None
    if layout.get(key):
        return layout[key]
    template = layout.get("template")
    template_layout = template.get("layout") if isinstance(template, dict) else None
    return template_layout.get(key) if isinstance(template_layout, dict) else None


def resolve_image_options(
    fig_dict: dict[str, Any],
    width: int | None,
    height: int | None,
    scale: float | None,
    defaults: Any,
) -> dict[str, Any]:
    """Width, height and scale as ``plotly.io._kaleido.to_image`` (plotly 6.8) resolves them.

    Order: the argument, then ``fig.layout``, then the layout template, then ``plotly.io.defaults``.
    Scale has no layout fallback.
    """
    return {
        "format": "png",
        "width": width or _layout_size(fig_dict, "width") or defaults.default_width,
        "height": height or _layout_size(fig_dict, "height") or defaults.default_height,
        "scale": scale or defaults.default_scale,
    }


def _run_in_fresh_thread(make_coro: Callable[[], Any]) -> Any:
    """Run a coroutine with ``asyncio.run`` on a new thread; return its result or re-raise its error."""
    # Each entry is (succeeded, value): the result, or the exception to re-raise here.
    q: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def run() -> None:
        try:
            q.put((True, asyncio.run(make_coro())))
        except Exception as exc:
            q.put((False, exc))

    thread = Thread(target=run)
    thread.start()
    thread.join()
    try:
        succeeded, value = q.get_nowait()
    except Empty:  # the worker died with a non-Exception before it could report
        raise RuntimeError("render thread ended without a result") from None
    if not succeeded:
        raise value
    return value


def _render_with_bundled_browser(
    fig: Any, browser: Path, width: int | None, height: int | None, scale: float | None
) -> bytes:
    try:
        import kaleido
        from plotly.io import defaults

        fig_dict = fig.to_dict() if hasattr(fig, "to_dict") else fig
        kopts: dict[str, Any] = {"path": str(browser), "mathjax": False}
        if defaults.plotlyjs:
            kopts["plotlyjs"] = defaults.plotlyjs
        opts: Any = resolve_image_options(fig_dict, width, height, scale, defaults)
        return _run_in_fresh_thread(
            lambda: kaleido.calc_fig(fig_dict, opts=opts, topojson=defaults.topojson, kopts=kopts)
        )
    except Exception:
        # Kaleido's ChromeNotFoundError text embeds the absolute browser path; show none of it.
        raise BundledBrowserUnavailableError() from None


def figure_to_png(
    fig: Any, *, width: int | None = None, height: int | None = None, scale: float | None = None
) -> bytes:
    """Render *fig* to PNG bytes.

    Light raises :class:`~guiskindose.edition.PngExportUnavailableError` before Kaleido is imported.
    A source or pip install calls ``fig.to_image`` unchanged. The frozen Full app renders with its
    bundled browser only and raises :class:`BundledBrowserUnavailableError` rather than fall back
    to any other browser.
    """
    if not png_export_available():
        raise PngExportUnavailableError()
    if not _is_frozen():
        return fig.to_image(format="png", width=width, height=height, scale=scale)
    browser = bundled_browser_for_render()
    if browser is None or not browser.is_file():
        raise BundledBrowserUnavailableError()
    return _render_with_bundled_browser(fig, browser, width, height, scale)
