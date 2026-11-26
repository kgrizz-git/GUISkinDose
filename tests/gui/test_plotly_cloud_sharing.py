"""Plotly "Share chart" must never be enabled by the app's figures or exports.

plotly.js 4.2 (in-app) adds a modebar button that uploads chart data to
``cloud.plotly.com``. NiceGUI hides it by leaving ``showSendToCloud`` at its
falsy default on every in-app plot, and this project never supplies a config
that overrides that to a truthy value.

The page itself builds each ``ui.plotly`` as ``ui.plotly({})`` and only fills in
a figure later through ``update_figure()``, so inspecting page elements proves
nothing. These tests therefore check the figure builders that feed
``ui.plotly``/``update_figure``: the dose map, the Results placeholder, the
Settings phantom preview and the Geometry preview. A returned figure dict may
carry a ``config`` entry; if it does, it must not enable sharing. The exported
standalone HTML is checked too, and a comment-stripped source gate rejects any
truthy ``showSendToCloud`` assignment under the package.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

pytest.importorskip("nicegui")

import guiskindose

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_PATIENT: dict = {
    "patient": {
        "patient_skin_cells": {"x": [0.0, 1.0, 0.0], "y": [0.0, 0.0, 1.0], "z": [0.0, 0.0, 0.0]},
        "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
    }
}

_SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".html", ".htm"}

# The key, optionally quoted/bracketed (``config["showSendToCloud"] = ...``), then
# ``:`` or ``=`` and the assigned value up to the next delimiter.
_CLOUD_SHARING_ASSIGNMENT = re.compile(r"""showSendToCloud\s*["'\]]*\s*[:=]\s*(?P<value>[^,;}\)\n]*)""")

# The only unquoted spellings that mean "do not enable sharing". Everything else -- 2,
# a variable, ``!0`` -- is treated as enabled. A quoted value is falsy only when it is
# exactly empty: in JavaScript "false", "0" and " " are non-empty strings, so truthy.
_CLEARLY_FALSY = {"false", "0", "!1", "null", "none", "undefined"}


def _preview_snapshot():
    """A Settings phantom-preview snapshot (human mesh, no RDSR needed)."""
    from guiskindose.gui.phantom_preview import PreviewSnapshot

    return PreviewSnapshot(
        phantom_model="human",
        human_mesh="hudfrid",
        patient_orientation="head_first_supine",
        scale_lat=1.0,
        scale_ap=1.0,
        scale_lon=1.0,
        d_lon=0.0,
        d_ver=0.0,
        d_lat=0.0,
    )


def _config_enables_cloud_sharing(config: object) -> bool:
    return isinstance(config, dict) and bool(config.get("showSendToCloud"))


def _is_clearly_falsy(value: str) -> bool:
    """Whether an assigned value is an explicit false/0/null/empty spelling."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1] == ""
    return text.lower() in _CLEARLY_FALSY


def _enabling_values(text: str) -> list[str]:
    """Return every assigned ``showSendToCloud`` value that is not clearly falsy."""
    return [
        match.group("value").strip()
        for match in _CLOUD_SHARING_ASSIGNMENT.finditer(text)
        if not _is_clearly_falsy(match.group("value"))
    ]


def _python_without_comments(text: str) -> str:
    """Blank out ``#`` comments by tokenizing, so a ``#`` inside a string stays put.

    If the text does not tokenize, it is returned unchanged: the gate then fails
    closed (a comment could trip it) rather than silently skipping the file.
    """
    try:
        comments = [tok for tok in tokenize.generate_tokens(io.StringIO(text).readline) if tok.type == tokenize.COMMENT]
    except (SyntaxError, tokenize.TokenError, IndentationError):
        return text
    lines = text.splitlines(keepends=True)
    for token in comments:
        row, start_col = token.start
        _, end_col = token.end
        line = lines[row - 1]
        lines[row - 1] = line[:start_col] + line[end_col:]
    return "".join(lines)


def _c_like_without_comments(text: str) -> str:
    """Drop ``//`` and ``/* ... */`` comments, leaving string literals intact.

    A small scanner rather than a regex, so ``"https://..."`` inside a string is not
    mistaken for a comment that would hide the rest of the line.
    """
    out: list[str] = []
    i, quote = 0, ""
    while i < len(text):
        char = text[i]
        if quote:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
            out.append(char)
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        else:
            out.append(char)
        i += 1
    return "".join(out)


def _stripped_source(suffix: str, text: str) -> str:
    """Strip comments for the file type, so a commented-out setting cannot trip the gate."""
    if suffix.lower() == ".py":
        return _python_without_comments(text)
    return _c_like_without_comments(text)


def test_config_check_flags_any_truthy_setting() -> None:
    """Guard the helper itself, so the figure tests below could actually fail."""
    assert _config_enables_cloud_sharing({"showSendToCloud": True})
    assert _config_enables_cloud_sharing({"showSendToCloud": 1})
    assert _config_enables_cloud_sharing({"showSendToCloud": "true"})
    assert not _config_enables_cloud_sharing({"showSendToCloud": False})
    assert not _config_enables_cloud_sharing({})
    assert not _config_enables_cloud_sharing(None)


def test_dosemap_fig_does_not_enable_cloud_sharing() -> None:
    """The figure fed to the Results ``ui.plotly`` via ``update_figure()``."""
    from guiskindose.gui.figures import make_dosemap_fig

    fig = make_dosemap_fig(explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=_PATIENT)

    assert fig is not None
    assert not _config_enables_cloud_sharing(fig.get("config"))


def test_placeholder_dosemap_fig_does_not_enable_cloud_sharing() -> None:
    """The pre-calculation Results placeholder, built from a Settings snapshot."""
    from guiskindose.gui.phantom_preview import make_placeholder_dosemap_fig

    fig = make_placeholder_dosemap_fig(_preview_snapshot())

    assert fig is not None
    assert not _config_enables_cloud_sharing(fig.get("config"))


def test_phantom_preview_fig_does_not_enable_cloud_sharing() -> None:
    """The Settings human-mesh preview, built from the same snapshot type."""
    from guiskindose.gui.phantom_preview import make_phantom_preview_fig

    fig = make_phantom_preview_fig(_preview_snapshot())

    assert fig is not None
    assert not _config_enables_cloud_sharing(fig.get("config"))


def test_geometry_fig_does_not_enable_cloud_sharing() -> None:
    """The Geometry figure that ``geometry_controller`` feeds to ``update_figure()``.

    Built in ``plot_setup`` mode from a bundled example exam, with the default
    human phantom, so no calculation or user interaction is involved.
    """
    from guiskindose import get_path_to_example_rdsr_files
    from guiskindose.gui.figures import make_geometry_fig
    from guiskindose.gui.helpers import load_rdsr
    from guiskindose.gui.state import state

    loaded, _ = load_rdsr(get_path_to_example_rdsr_files() / "philips_allura_clarity_u104.dcm", state)
    assert loaded

    fig = make_geometry_fig("plot_setup", 0)

    assert fig is not None
    assert not _config_enables_cloud_sharing(fig.get("config"))


def test_exported_dose_map_html_does_not_enable_cloud_sharing() -> None:
    """The exported plot call sets ``showSendToCloud`` to false explicitly.

    Absence is not enough: standalone plotly.js 4.0 (bundled by plotly 7) shows "Share
    chart" by default, and NiceGUI's in-app default does not reach exports.
    """
    from guiskindose.gui.figures import make_dosemap_html

    html = make_dosemap_html(explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=_PATIENT).decode("utf-8")

    # The last <script> is the Plotly.newPlot(...) call; the inlined library
    # bundle before it mentions the option in its own schema text.
    call_script = html[html.rfind("<script") :]
    assert "Plotly.newPlot" in call_script
    assert re.search(r'"showSendToCloud"\s*:\s*false', call_script)


@pytest.mark.parametrize(
    "snippet",
    [
        'config = {"showSendToCloud": True}',
        'config = {"showSendToCloud": true}',
        "showSendToCloud: TRUE,",
        "config.showSendToCloud = !0;",
        "showSendToCloud: 1",
        "showSendToCloud: 2",
        "config = {'showSendToCloud': 'true'}",
        "config = {'showSendToCloud': '1'}",
        'config = {"showSendToCloud": "yes"}',
        "config.showSendToCloud = enabled;",
        'config["showSendToCloud"] = True',
        'config = {"showSendToCloud": "false"}',
        "config = {'showSendToCloud': '0'}",
        'config = {"showSendToCloud": " "}',
    ],
)
def test_source_gate_flags_any_value_that_is_not_clearly_falsy(snippet: str) -> None:
    """Positive cases: every spelling, number, or variable that enables sharing is caught."""
    assert _enabling_values(_stripped_source(".py", snippet)) != []


@pytest.mark.parametrize(
    "snippet",
    [
        'config = {"showSendToCloud": False}',
        'config = {"showSendToCloud": false}',
        'config = {"showSendToCloud": 0}',
        "config.showSendToCloud = !1;",
        'config = {"showSendToCloud": null}',
        'config = {"showSendToCloud": None}',
        'config = {"showSendToCloud": ""}',
    ],
)
def test_source_gate_allows_explicit_falsy_values(snippet: str) -> None:
    """Negative cases: an explicit false/0/null/empty string is not an offender."""
    assert _enabling_values(_stripped_source(".py", snippet)) == []


@pytest.mark.parametrize(
    "suffix, snippet",
    [
        (".py", "# never set showSendToCloud: true here\nvalue = 1\n"),
        (".js", "// never set showSendToCloud: true here\nconst value = 1;\n"),
        (".mjs", "/* never set showSendToCloud: true */\nconst value = 1;\n"),
        (".html", "<script>// never set showSendToCloud: true here\n</script>\n"),
    ],
)
def test_source_gate_ignores_comments(suffix: str, snippet: str) -> None:
    """A commented-out assignment (``#``, ``//``, ``/* */``) is not an offender."""
    assert _enabling_values(_stripped_source(suffix, snippet)) == []


def test_js_comment_stripping_keeps_urls_in_strings() -> None:
    """A ``//`` inside a string (a URL) must not hide an assignment later on the line."""
    text = 'const opts = {url: "https://plot.ly/x", showSendToCloud: true};\n'
    assert _enabling_values(_stripped_source(".js", text)) == ["true"]


def test_python_comment_stripping_keeps_string_literals() -> None:
    """Tokenizing must not treat a literal containing ``#`` as a comment."""
    text = 'config = {"showSendToCloud": True}  # ok\nother = "# not a comment"\n'
    assert _enabling_values(_stripped_source(".py", text)) == ["True"]


def test_no_source_file_enables_cloud_sharing() -> None:
    """A comment-stripped grep gate: nothing under the package enables sharing."""
    package_root = Path(guiskindose.__file__).parent
    offenders = []
    for path in package_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if _enabling_values(_stripped_source(path.suffix, text)):
            offenders.append(path.relative_to(package_root).as_posix())
    assert offenders == []
