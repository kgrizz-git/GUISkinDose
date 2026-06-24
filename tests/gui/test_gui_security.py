"""
Security regression tests for the MyPySkinDose GUI.

Covers two hardening fixes:
  1. Browser-mode server binds to localhost (127.0.0.1) by default, so PHI-derived
     data in the shared, unauthenticated state is not exposed on the network unless
     a host is explicitly opted into.
  2. Uploads are size-capped (client-side via max_file_size and server-side via the
     guard in handle_upload) to bound memory/disk use from a hostile upload.
"""

from __future__ import annotations

import pytest
from nicegui import ui
from nicegui.testing import User

import mypyskindose.gui.app as gui_app
from mypyskindose.gui.tabs.upload import MAX_UPLOAD_BYTES, upload_exceeds_limit

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


# ── 1. network binding ──────────────────────────────────────────────────────
def test_run_gui_binds_localhost_by_default(monkeypatch) -> None:
    """run_gui() must pass host=127.0.0.1 to ui.run when no host is given."""
    captured: dict = {}
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    gui_app.run_gui(native=False)
    assert captured["host"] == "127.0.0.1"


def test_run_gui_host_is_opt_in(monkeypatch) -> None:
    """An explicit host (LAN serving) is honored and passed through verbatim."""
    captured: dict = {}
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    gui_app.run_gui(native=False, host="0.0.0.0")
    assert captured["host"] == "0.0.0.0"


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
