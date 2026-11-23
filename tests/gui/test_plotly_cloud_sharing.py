"""Plotly "Share chart" must never be enabled by the app or its exports.

plotly.js 4.2 (in-app) adds a modebar button that uploads chart data to
``cloud.plotly.com``. NiceGUI hides it by setting ``showSendToCloud: false`` on
every in-app plot, and this project never supplies a config that overrides that
back to ``true``. The exported standalone HTML must not enable it either.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from nicegui.testing import User

import guiskindose

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_PATIENT: dict = {
    "patient": {
        "patient_skin_cells": {"x": [0.0, 1.0, 0.0], "y": [0.0, 0.0, 1.0], "z": [0.0, 0.0, 0.0]},
        "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
    }
}

# Python dict / HTML-JSON / minified-JS truthy spellings of an enabled config.
# The optional ``"]`` also catches subscript assignments such as ``config["showSendToCloud"] = True``.
_ENABLES_CLOUD_SHARING = re.compile(r"""showSendToCloud\s*["'\]]*\s*[:=]\s*(True|true|TRUE|!0|1)\b""")
_SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".html", ".htm"}


def _config_enables_cloud_sharing(config: object) -> bool:
    return isinstance(config, dict) and bool(config.get("showSendToCloud"))


def test_config_check_flags_any_truthy_setting() -> None:
    """Guard the helper itself, so the in-app test below can actually fail."""
    assert _config_enables_cloud_sharing({"showSendToCloud": True})
    assert _config_enables_cloud_sharing({"showSendToCloud": 1})
    assert not _config_enables_cloud_sharing({"showSendToCloud": False})
    assert not _config_enables_cloud_sharing({})
    assert not _config_enables_cloud_sharing(None)


@pytest.mark.asyncio
async def test_in_app_plots_do_not_enable_cloud_sharing(user: User) -> None:
    """No ``ui.plotly`` element on the page carries a config that overrides NiceGUI's ``false``."""
    from nicegui import ui

    await user.open("/")
    assert user.client is not None
    plots = [el for el in user.client.elements.values() if isinstance(el, ui.plotly)]

    assert plots  # Geometry, Settings preview and Results dose maps are built at page load
    for plot in plots:
        figure = plot.figure if isinstance(plot.figure, dict) else plot.figure.to_plotly_json()
        assert not _config_enables_cloud_sharing(figure.get("config"))


def test_exported_dose_map_html_does_not_enable_cloud_sharing() -> None:
    """The exported plot call sets no ``showSendToCloud``, so it cannot enable it."""
    from guiskindose.gui.figures import make_dosemap_html

    html = make_dosemap_html(explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=_PATIENT).decode("utf-8")

    # The last <script> is the Plotly.newPlot(...) call; the inlined library
    # bundle before it mentions the option in its own schema text.
    call_script = html[html.rfind("<script") :]
    assert "Plotly.newPlot" in call_script
    assert "showSendToCloud" not in call_script


def test_no_source_file_enables_cloud_sharing() -> None:
    """A grep gate: nothing under the package sets ``showSendToCloud`` to true."""
    package_root = Path(guiskindose.__file__).parent
    offenders = []
    for path in package_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _ENABLES_CLOUD_SHARING.search(text):
            offenders.append(path.relative_to(package_root).as_posix())
    assert offenders == []
