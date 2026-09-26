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

import inspect
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from nicegui import ui
from nicegui.testing import User

import guiskindose.gui.app as gui_app
from guiskindose.gui.tabs.upload import MAX_UPLOAD_BYTES, upload_exceeds_limit

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_REAL_LOOPBACK_PORT_IS_FREE = gui_app._loopback_port_is_free


@pytest.fixture(autouse=True)
def _default_port_free(monkeypatch):
    """Keep default-port tests hermetic when 8765 is busy on the dev machine."""
    monkeypatch.setattr(gui_app, "_loopback_port_is_free", lambda _p: True)


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
_REMOTE_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_BLOCKED_FONT_HOSTS = frozenset({"fonts.googleapis.com", "fonts.gstatic.com"})


def _blocked_remote_hosts(text: str) -> set[str]:
    """Return the blocked third-party font hosts referenced by exact hostname."""
    hosts = set()
    for match in _REMOTE_URL_RE.findall(text):
        host = urlparse(match).hostname or ""
        if host in _BLOCKED_FONT_HOSTS:
            hosts.add(host)
    return hosts


def test_icon_font_is_bundled_locally() -> None:
    """The icon font must come from the package, never from Google Fonts."""
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
    gui_dir = Path(gui_app.__file__).resolve().parent
    remote_hits = {
        str(path): sorted(_blocked_remote_hosts(path.read_text(encoding="utf-8")))
        for path in sorted(gui_dir.rglob("*.py"))
    }
    remote_hits = {path: hosts for path, hosts in remote_hits.items() if hosts}
    assert not remote_hits, f"remote font refs in GUI modules: {remote_hits}"


def test_run_gui_registers_bundled_static_files(monkeypatch) -> None:
    """run_gui() must mount the package static dir before starting the server."""
    captured: dict = {}
    # Reset on this module's own reference: the user-simulation harness
    # reloads gui.app, so conftest cannot reset it for us (see below).
    gui_app._STATIC_REGISTERED = False
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


def test_static_registration_is_idempotent(monkeypatch) -> None:
    """Repeated run_gui() calls must not stack duplicate static routes."""
    calls: list = []
    # Same-reference reset: gui.app is reloaded by the user-simulation
    # harness, so this module's reference may be stale relative to
    # sys.modules — reset and call through the identical object.
    gui_app._STATIC_REGISTERED = False
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: None)
    monkeypatch.setattr(
        gui_app.app, "add_static_files", lambda *args, **kw: calls.append(args)
    )
    gui_app.register_gui_static_files()
    gui_app.register_gui_static_files()
    assert len(calls) == 1


# ── 4. loopback security wiring ─────────────────────────────────────────────
def test_run_gui_registers_security_middleware_and_token_url(monkeypatch, capsys) -> None:
    """Browser mode installs Host/Origin/token controls and opens the token URL."""
    from guiskindose.gui.loopback_security import LoopbackSecurityMiddleware

    captured: dict = {}
    opened: list = []
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(
        gui_app.app, "add_middleware", lambda cls, **_kw: captured.setdefault("middleware", cls)
    )
    monkeypatch.setattr(gui_app, "_open_browser_when_ready", lambda url, **_kw: opened.append(url))
    gui_app.run_gui(native=False)
    assert captured["middleware"] is LoopbackSecurityMiddleware
    assert captured["show"] is False
    assert captured["port"] == 8765
    assert len(opened) == 1
    assert opened[0].startswith("http://127.0.0.1:8765/?token=")
    assert "open http://127.0.0.1:8765/?token=" in capsys.readouterr().out


@pytest.mark.parametrize("port,expected", [(None, 8765), (9999, 9999)])
def test_resolve_port_defaults_and_explicit(port: int | None, expected: int) -> None:
    assert gui_app._resolve_port(port) == expected


def test_resolve_port_default_falls_back_to_next_free_port(monkeypatch, capsys) -> None:
    """A busy default moves to the next free port and says so."""
    busy = {8765, 8766}
    monkeypatch.setattr(gui_app, "_loopback_port_is_free", lambda p: p not in busy)
    assert gui_app._resolve_port(None) == 8767
    assert "Port 8765 is in use; using port 8767" in capsys.readouterr().out


def test_resolve_port_default_falls_back_to_os_assigned(monkeypatch, capsys) -> None:
    """If the whole fallback span is busy, the OS picks a loopback port."""
    monkeypatch.setattr(gui_app, "_loopback_port_is_free", lambda _p: False)
    monkeypatch.setattr(gui_app, "_os_assigned_loopback_port", lambda: 54321)
    assert gui_app._resolve_port(None) == 54321
    assert "using port 54321" in capsys.readouterr().out


def test_resolve_port_explicit_port_never_falls_back(monkeypatch) -> None:
    """An explicit --port is used as-is even when busy (fails loudly at bind)."""
    monkeypatch.setattr(gui_app, "_loopback_port_is_free", lambda _p: False)
    assert gui_app._resolve_port(9999) == 9999


def test_loopback_port_is_free_detects_busy_port() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        busy_port = holder.getsockname()[1]
        assert _REAL_LOOPBACK_PORT_IS_FREE(busy_port) is False


def test_run_gui_default_port_fallback_scopes_security(monkeypatch) -> None:
    """A fallback port reaches ui.run and the Host allowlist, not the default."""
    from guiskindose.gui.loopback_security import get_loopback_security_config

    captured: dict = {}
    monkeypatch.setattr(gui_app, "_loopback_port_is_free", lambda p: p != 8765)
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(gui_app, "_open_browser_when_ready", lambda url, **_kw: None)
    gui_app.run_gui(native=False)
    assert captured["port"] == 8766
    assert captured["host"] == "127.0.0.1"
    config = get_loopback_security_config()
    assert config is not None
    assert "127.0.0.1:8766" in config.allowed_hosts
    assert "127.0.0.1:8765" not in config.allowed_hosts


def test_resolve_port_zero_picks_free_loopback_port() -> None:
    port = gui_app._resolve_port(0)
    assert isinstance(port, int) and 1 <= port <= 65535


@pytest.mark.parametrize("port", [-1, 65536, 100000])
def test_resolve_port_rejects_out_of_range(port: int) -> None:
    with pytest.raises(ValueError, match="gui_port_out_of_range"):
        gui_app._resolve_port(port)


def test_run_gui_honors_explicit_port(monkeypatch) -> None:
    """An explicit port reaches ui.run, the token URL, and the Host allowlist."""
    from guiskindose.gui.loopback_security import get_loopback_security_config

    captured: dict = {}
    opened: list = []
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(gui_app, "_open_browser_when_ready", lambda url, **_kw: opened.append(url))
    gui_app.run_gui(native=False, port=9999)
    assert captured["port"] == 9999
    assert opened[0].startswith("http://127.0.0.1:9999/?token=")
    config = get_loopback_security_config()
    assert config is not None
    assert "127.0.0.1:9999" in config.allowed_hosts
    assert "http://127.0.0.1:9999" in config.allowed_origins


def test_run_gui_native_skips_token_but_keeps_host_checks(monkeypatch) -> None:
    """Native mode enforces Host/Origin without the token (trusted embedded client)."""
    from guiskindose.gui.loopback_security import get_loopback_security_config

    captured: dict = {}
    opened: list = []
    monkeypatch.setattr(gui_app.ui, "run", lambda **kw: captured.update(kw))
    monkeypatch.setattr(gui_app, "_configure_native_window", lambda: (1024, 768))
    monkeypatch.setattr(gui_app, "_register_native_focus_handler", lambda: None)
    monkeypatch.setattr(gui_app, "_open_browser_when_ready", lambda *a, **k: opened.append(a))
    gui_app.run_gui(native=True)
    assert captured["show"] is True
    assert opened == []
    config = get_loopback_security_config()
    assert config is not None
    assert config.require_token is False


def test_wait_for_port_detects_open_and_closed_ports() -> None:
    """The auto-open gate fires only after a real loopback connect."""
    import socket as socket_module

    server = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        assert gui_app._wait_for_port("127.0.0.1", port, timeout=5.0) is True
    finally:
        server.close()
    assert gui_app._wait_for_port("127.0.0.1", port, timeout=0.3) is False


def test_browser_auto_open_waits_for_server(monkeypatch) -> None:
    """The opener thread fires only once the port accepts connections."""
    import time as time_module

    opened: list = []
    monkeypatch.setattr(gui_app.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(gui_app, "_wait_for_port", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_app, "probe_own_server", lambda *args, **kwargs: True)
    gui_app._open_browser_when_ready("http://127.0.0.1:8765/?token=t")
    deadline = time_module.monotonic() + 5.0
    while not opened and time_module.monotonic() < deadline:
        time_module.sleep(0.05)
    assert opened == ["http://127.0.0.1:8765/?token=t"]


def test_browser_auto_open_refuses_foreign_listener(monkeypatch, capsys) -> None:
    """A squatter on the port gets guidance, never the token URL."""
    import time as time_module

    opened: list = []
    monkeypatch.setattr(gui_app.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(gui_app, "_wait_for_port", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_app, "probe_own_server", lambda *args, **kwargs: False)
    gui_app._open_browser_when_ready("http://127.0.0.1:8765/?token=t")
    deadline = time_module.monotonic() + 5.0
    seen = ""
    while "not serving this GUI" not in seen and time_module.monotonic() < deadline:
        time_module.sleep(0.05)
        seen += capsys.readouterr().out
    assert opened == []
    assert "not serving this GUI" in seen


def test_browser_auto_open_stays_quiet_without_server(monkeypatch, capsys) -> None:
    """No server, no browser window — and a failed open degrades to a message."""
    import time as time_module

    opened: list = []
    monkeypatch.setattr(gui_app, "_wait_for_port", lambda *args, **kwargs: False)
    gui_app._open_browser_when_ready("http://127.0.0.1:8765/?token=t")
    time_module.sleep(0.3)
    assert opened == []
    assert capsys.readouterr().out == ""

    def _boom(_url: str) -> None:
        raise RuntimeError("no browser")

    monkeypatch.setattr(gui_app, "_wait_for_port", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_app, "probe_own_server", lambda *args, **kwargs: True)
    monkeypatch.setattr(gui_app.webbrowser, "open", _boom)
    gui_app._open_browser_when_ready("http://127.0.0.1:8765/?token=t")
    deadline = time_module.monotonic() + 5.0
    seen = ""
    while "Open the GUI manually" not in seen and time_module.monotonic() < deadline:
        time_module.sleep(0.05)
        seen += capsys.readouterr().out
    assert "Open the GUI manually: http://127.0.0.1:8765/?token=t" in seen
