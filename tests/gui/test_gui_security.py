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
