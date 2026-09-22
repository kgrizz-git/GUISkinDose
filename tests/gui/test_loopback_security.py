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


@pytest.fixture()
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
    assert sent and sent[0]["type"] == "websocket.accept"


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


def test_malformed_cookie_treated_as_no_session(live_config, monkeypatch) -> None:
    _, _ = live_config
    import guiskindose.gui.loopback_security as loopback_security

    class _Unparseable:
        def load(self, _header: str) -> None:
            raise ValueError("bad cookie")

    monkeypatch.setattr(loopback_security, "SimpleCookie", lambda: _Unparseable())
    sent = asyncio.run(_run(LoopbackSecurityMiddleware(_ok_app), _http_scope(cookie="x=y")))
    assert _status(sent) == 403
