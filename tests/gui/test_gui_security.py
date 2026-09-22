"""
Security regression tests for the GUISkinDose GUI.

Covers two hardening fixes:
  1. Browser-mode server always binds to localhost (127.0.0.1): non-loopback
     hosts are refused outright, since PHI-derived data lives in a shared,
     unauthenticated process-global state.
  2. Uploads are size-capped (client-side via max_file_size and server-side via the
     guard in handle_upload) to bound memory/disk use from a hostile upload.
"""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

import guiskindose.gui.app as gui_app
from guiskindose.gui.tabs.upload import MAX_UPLOAD_BYTES, upload_exceeds_limit

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


# ── 1. loopback-only binding ───────────────────────────────────────────────
def test_run_gui_binds_localhost_by_default(monkeypatch) -> None:
    """run_gui() must pass host=127.0.0.1 to ui.run when no host is given."""
    captured: dict = {}
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    gui_app.run_gui(native=False)
    assert captured["host"] == "127.0.0.1"


def test_run_gui_normalizes_localhost_to_loopback_literal(monkeypatch) -> None:
    """'localhost' must bind the literal 127.0.0.1, never via the resolver."""
    captured: dict = {}
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    gui_app.run_gui(native=False, host="localhost")
    assert captured["host"] == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.10", "::1", "example.com"])
def test_run_gui_refuses_non_loopback_binding(monkeypatch, host: str) -> None:
    """Any non-127.0.0.1 host is refused: the GUI never serves off-host."""
    monkeypatch.setattr(gui_app.ui, "run", lambda **_kw: None)
    with pytest.raises(ValueError, match="non_loopback_gui_binding_refused"):
        gui_app.run_gui(native=False, host=host)


# ── 2. upload size cap ──────────────────────────────────────────────────────
def test_upload_size_guard_boundary() -> None:
    """The server-side guard rejects only payloads strictly over the limit."""
    limit = MAX_UPLOAD_BYTES
    assert upload_exceeds_limit(0) is False
    assert upload_exceeds_limit(limit) is False
    assert upload_exceeds_limit(limit + 1) is True


@pytest.mark.asyncio
async def test_uploader_has_max_file_size(user: User) -> None:
    """The rendered uploader carries the client-side max-file-size cap."""
    await user.open("/")
    uploads = list(user.find(ui.upload).elements)
    assert uploads, "no ui.upload element rendered on the upload tab"
    assert any(
        u._props.get("max-file-size") == MAX_UPLOAD_BYTES for u in uploads
    ), "uploader is missing the MAX_UPLOAD_BYTES max-file-size prop"


# ── 3. no third-party requests ──────────────────────────────────────────────
def test_icon_font_is_bundled_locally() -> None:
    """The icon font must come from the package, never from Google Fonts."""
    import inspect
    from pathlib import Path

    href = gui_app.material_symbols_stylesheet_href()
    assert not href.startswith("http"), f"remote stylesheet: {href}"
    fonts_dir = Path(gui_app.__file__).resolve().parent / "static" / "fonts"
    css_path = fonts_dir / Path(href).name
    assert css_path.is_file(), f"missing bundled stylesheet: {css_path}"
    css = css_path.read_text(encoding="utf-8")
    assert "http" not in css, "bundled stylesheet still references a remote URL"
    for line in css.splitlines():
        if "url(" in line:
            local = line.split("url(", 1)[1].split(")", 1)[0].strip().strip("'\"")
            assert (fonts_dir / local).is_file(), f"missing bundled font: {local}"
    module_source = inspect.getsource(gui_app)
    assert "fonts.googleapis.com" not in module_source
    assert "fonts.gstatic.com" not in module_source


def test_run_gui_registers_bundled_static_files(monkeypatch) -> None:
    """run_gui() must mount the package static dir before starting the server."""
    from pathlib import Path

    captured: dict = {}
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(
        gui_app.app,
        "add_static_files",
        lambda url_path, local_dir, **_kw: captured.setdefault("static", (url_path, local_dir)),
    )
    gui_app.run_gui(native=False)
    url_path, local_dir = captured["static"]
    assert url_path == "/guiskindose-static"
    assert Path(local_dir).is_dir()
    assert gui_app.material_symbols_stylesheet_href().startswith(url_path)
