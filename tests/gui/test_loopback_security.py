"""Unit tests for the loopback security middleware (no server needed)."""

from __future__ import annotations

import asyncio

import pytest

from guiskindose.gui.loopback_security import (
    SESSION_COOKIE_NAME,
    LoopbackSecurityConfig,
    LoopbackSecurityMiddleware,
    configure_loopback_security,
    generate_launch_token,
)


async def _ok_app(scope: dict, receive, send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _http_scope(
    *,
    host: str = "127.0.0.1:8765",
    origin: str | None = None,
    cookie: str = "",
    path: str = "/",
    query: bytes = b"",
    method: str = "GET",
) -> dict:
    headers = [(b"host", host.encode("latin-1"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("latin-1")))
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))
    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": query,
        "headers": headers,
    }


def _ws_scope(*, host: str = "127.0.0.1:8765", origin: str = "", cookie: str = "") -> dict:
    headers = [(b"host", host.encode("latin-1"))]
    if origin:
        headers.append((b"origin", origin.encode("latin-1")))
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))
    return {"type": "websocket", "path": "/socket.io/", "headers": headers}


@pytest.fixture
def live_config():
    token, config = generate_launch_token()
    configure_loopback_security(config)
    yield token, config
    configure_loopback_security(None)


async def _run(mw: LoopbackSecurityMiddleware, scope: dict) -> list[dict]:
    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    await mw(scope, receive, send)
    return sent


def _status(sent: list[dict]) -> int | None:
    for message in sent:
        if message["type"] == "http.response.start":
            return message["status"]
        if message["type"] == "websocket.close":
            return message["code"]
    return None


def _set_cookie(sent: list[dict]) -> str:
    for message in sent:
        if message["type"] == "http.response.start":
            for name, value in message.get("headers", []):
                if name == b"set-cookie":
                    return value.decode("ascii").split(";", 1)[0]
    raise AssertionError("no set-cookie header")


def test_passthrough_without_config() -> None:
    configure_loopback_security(None)
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _http_scope(host="evil.com")))
    assert _status(sent) == 200


def test_bad_host_rejected_http(live_config) -> None:
    _, _ = live_config
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _http_scope(host="evil.com")))
    assert _status(sent) == 400


def test_bad_host_rejected_websocket(live_config) -> None:
    _, _ = live_config
    sent = asyncio.run(
        _run(LoopbackSecurityMiddleware(_ok_app), _ws_scope(host="evil.com", origin="http://evil.com"))
    )
    assert _status(sent) == 4403


def test_websocket_requires_allowlisted_origin(live_config) -> None:
    _, _ = live_config
    mw = LoopbackSecurityMiddleware(_ok_app)
    assert _status(asyncio.run(_run(mw, _ws_scope(origin="http://evil.com")))) == 4403
    assert _status(asyncio.run(_run(mw, _ws_scope()))) == 4403


def test_websocket_missing_origin_with_session_passes(live_config) -> None:
    """Browsers always send Origin, so a missing one is a non-browser client:
    admitted with a session, rejected without (browser mode)."""
    token, _ = live_config
    mw = LoopbackSecurityMiddleware(_ok_app)
    assert _status(asyncio.run(_run(mw, _ws_scope()))) == 4403
    sent = asyncio.run(_run(mw, _http_scope(query=f"token={token}".encode("ascii"))))
    cookie = _set_cookie(sent)
    sent = asyncio.run(_run(mw, _ws_scope(cookie=cookie)))
    assert sent
    assert sent[0]["type"] == "websocket.accept"


def test_websocket_requires_session_cookie(live_config) -> None:
    """Sockets skip nothing: no cookie (or a forged one) means no socket."""
    token, _ = live_config
    mw = LoopbackSecurityMiddleware(_ok_app)
    origin = "http://127.0.0.1:8765"
    assert _status(asyncio.run(_run(mw, _ws_scope(origin=origin)))) == 4403
    assert (
        _status(
            asyncio.run(_run(mw, _ws_scope(origin=origin, cookie=f"{SESSION_COOKIE_NAME}=tampered")))
        )
        == 4403
    )
    sent = asyncio.run(_run(mw, _http_scope(query=f"token={token}".encode("ascii"))))
    cookie = _set_cookie(sent)
    sent = asyncio.run(_run(mw, _ws_scope(origin=origin, cookie=cookie)))
    assert sent
    assert sent[0]["type"] == "websocket.accept"


def test_native_websocket_needs_no_cookie() -> None:
    """Native exemption covers sockets too (Host/Origin still enforced)."""
    configure_loopback_security(LoopbackSecurityConfig(require_token=False))
    try:
        sent = asyncio.run(
            _run(
                LoopbackSecurityMiddleware(_ok_app),
                _ws_scope(origin="http://127.0.0.1:8765"),
            )
        )
        assert sent
        assert sent[0]["type"] == "websocket.accept"
        sent = asyncio.run(
            _run(
                LoopbackSecurityMiddleware(_ok_app),
                _ws_scope(origin="http://evil.com"),
            )
        )
        assert _status(sent) == 4403
        sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _ws_scope()))
        assert sent
        assert sent[0]["type"] == "websocket.accept"
    finally:
        configure_loopback_security(None)


def test_bootstrap_issues_cookie_then_session_passes(live_config) -> None:
    token, _ = live_config
    mw = LoopbackSecurityMiddleware(_ok_app)
    sent = asyncio.run(_run(mw, _http_scope(query=f"token={token}".encode("ascii"))))
    assert _status(sent) == 302
    cookie = _set_cookie(sent)
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert b"HttpOnly" in sent[0]["headers"][1][1]
    sent = asyncio.run(_run(mw, _http_scope(cookie=cookie)))
    assert _status(sent) == 200
    assert sent[1] == {"type": "http.response.body", "body": b"ok"}


def test_bootstrap_redirect_strips_token(live_config) -> None:
    token, _ = live_config
    sent = asyncio.run(
        _run(
            LoopbackSecurityMiddleware(_ok_app),
            _http_scope(path="/", query=f"token={token}&foo=bar".encode("ascii")),
        )
    )
    locations = [
        value
        for message in sent
        if message["type"] == "http.response.start"
        for name, value in message.get("headers", [])
        if name == b"location"
    ]
    assert locations == [b"/?foo=bar"]


def test_bootstrap_redirect_preserves_query_encoding(live_config) -> None:
    """Values with '+'/'%20' must round-trip, not corrupt into spaces."""
    token, _ = live_config
    sent = asyncio.run(
        _run(
            LoopbackSecurityMiddleware(_ok_app),
            _http_scope(path="/", query=f"token={token}&note=a%2Fb+c".encode("ascii")),
        )
    )
    locations = [
        value
        for message in sent
        if message["type"] == "http.response.start"
        for name, value in message.get("headers", [])
        if name == b"location"
    ]
    assert locations == [b"/?note=a%2Fb+c"]


def test_bootstrap_redirect_uses_raw_path_bytes(live_config) -> None:
    """Non-latin-1 path characters must survive the redirect unmangled."""
    token, _ = live_config
    scope = _http_scope(path="/caf\u00e9", query=f"token={token}".encode("ascii"))
    scope["raw_path"] = "/caf%C3%A9".encode("ascii")
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), scope))
    locations = [
        value
        for message in sent
        if message["type"] == "http.response.start"
        for name, value in message.get("headers", [])
        if name == b"location"
    ]
    assert locations == ["/caf%C3%A9".encode("ascii")]


def test_wrong_token_and_tampered_cookie_rejected(live_config) -> None:
    _, _ = live_config
    mw = LoopbackSecurityMiddleware(_ok_app)
    assert _status(asyncio.run(_run(mw, _http_scope(query=b"token=wrong")))) == 403
    assert _status(asyncio.run(_run(mw, _http_scope(cookie=f"{SESSION_COOKIE_NAME}=tampered")))) == 403
    assert _status(asyncio.run(_run(mw, _http_scope()))) == 403


def test_state_changing_request_with_foreign_origin_rejected(live_config) -> None:
    token, _ = live_config
    mw = LoopbackSecurityMiddleware(_ok_app)
    sent = asyncio.run(_run(mw, _http_scope(query=f"token={token}".encode("ascii"))))
    cookie = _set_cookie(sent)
    sent = asyncio.run(
        _run(mw, _http_scope(method="POST", origin="http://evil.com", cookie=cookie))
    )
    assert _status(sent) == 403


def test_native_style_config_skips_token(live_config) -> None:
    _, _ = live_config
    configure_loopback_security(LoopbackSecurityConfig(require_token=False))
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _http_scope()))
    assert _status(sent) == 200


def test_non_http_scope_passes_through(live_config) -> None:
    _, _ = live_config
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), {"type": "lifespan"}))
    assert _status(sent) == 200


def test_non_ascii_query_rejected(live_config) -> None:
    _, _ = live_config
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _http_scope(query=b"\xff\xfetoken=x")))
    assert _status(sent) == 403


def test_percent_encoded_unicode_token_rejected_without_error(live_config) -> None:
    """%C3%A9 decodes past the ASCII-bytes guard; it must 403, not 500."""
    _, _ = live_config
    sent = asyncio.run(
        _run(LoopbackSecurityMiddleware(_ok_app), _http_scope(query=b"token=%C3%A9"))
    )
    assert _status(sent) == 403


def test_malformed_cookie_treated_as_no_session(live_config, monkeypatch) -> None:
    _, _ = live_config
    import guiskindose.gui.loopback_security as loopback_security

    class _Unparseable:
        def load(self, _header: str) -> None:
            raise ValueError("bad cookie")

    monkeypatch.setattr(loopback_security, "SimpleCookie", lambda: _Unparseable())
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _http_scope(cookie="x=y")))
    assert _status(sent) == 403


def _config_for_port(port: int, *, require_token: bool = True):
    from guiskindose.gui.loopback_security import LoopbackSecurityConfig

    return LoopbackSecurityConfig.for_port(port, require_token=require_token)


def test_custom_port_scopes_rejection(live_config) -> None:
    """A config for :9999 rejects :8765 Host/Origin values, accepts its own."""
    token, live = live_config
    from dataclasses import replace

    import guiskindose.gui.loopback_security as loopback_security

    configure_loopback_security(
        replace(_config_for_port(9999), launch_token_hash=live.launch_token_hash)
    )
    try:
        mw = LoopbackSecurityMiddleware(_ok_app)
        assert (
            _status(
                asyncio.run(
                    _run(
                        mw,
                        _http_scope(
                            host="127.0.0.1:8765",
                            origin="http://127.0.0.1:8765",
                            query=f"token={token}".encode("ascii"),
                        ),
                    )
                )
            )
            == 400
        )
        sent = asyncio.run(
            _run(mw, _http_scope(host="127.0.0.1:9999", query=f"token={token}".encode("ascii")))
        )
        assert _status(sent) == 302
        cookie = _set_cookie(sent)
        sent = asyncio.run(
            _run(
                mw,
                _ws_scope(
                    host="127.0.0.1:9999", origin="http://127.0.0.1:9999", cookie=cookie
                ),
            )
        )
        assert sent
        assert sent[0]["type"] == "websocket.accept"
        sent = asyncio.run(
            _run(
                mw,
                _ws_scope(
                    host="127.0.0.1:9999", origin="http://127.0.0.1:8765", cookie=cookie
                ),
            )
        )
        assert _status(sent) == 4403
    finally:
        configure_loopback_security(None)
    assert loopback_security.get_loopback_security_config() is None


def test_probe_own_server_matches_refusal_signature() -> None:
    """The auto-open gate opens only for our exact 403 refusal body."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from guiskindose.gui.loopback_security import _FORBIDDEN_BODY, probe_own_server

    def _make_handler(status: int, body: bytes) -> type[BaseHTTPRequestHandler]:
        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        return _Handler

    def _run_server(status: int, body: bytes) -> int:
        server = HTTPServer(("127.0.0.1", 0), _make_handler(status, body))
        port = server.server_address[1]
        assert isinstance(port, int)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.daemon = True
        thread.start()
        return port

    own = _run_server(403, _FORBIDDEN_BODY)
    assert probe_own_server("127.0.0.1", own) is True
    assert probe_own_server("127.0.0.1", _run_server(403, b"forbidden")) is False
    assert probe_own_server("127.0.0.1", _run_server(200, b"ok")) is False
    import socket as socket_module

    with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    assert isinstance(closed_port, int)
    assert probe_own_server("127.0.0.1", closed_port, timeout=0.5) is False
