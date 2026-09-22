"""Loopback-only hardening for the GUISkinDose GUI server.

Binding to ``127.0.0.1`` keeps remote machines from connecting, but it is not
an authentication boundary: a malicious webpage in the operator's own browser
can still reach the fixed loopback port (blind requests, cross-origin
websocket attempts, DNS rebinding), and any local OS user can connect
directly. This module closes those paths with three layered controls,
registered by ``run_gui()`` before ``ui.run()``:

1. **Strict Host validation** — only the loopback authority is accepted, so a
   DNS-rebinding origin (``evil.com`` resolving to ``127.0.0.1``) is rejected
   before touching app code. Stops remote pages; local processes can forge
   ``Host:`` and are not the target here.
2. **Origin validation** — a present-but-foreign ``Origin`` on websockets
   or HTTP is a cross-site page (browsers always send ``Origin``). Sockets
   additionally need the session whenever tokens are on — an allowlisted
   ``Origin`` alone proves nothing against local processes, which can forge
   it. Native mode skips the session check, tolerating embedded webviews
   that omit the header (remote pages cannot omit it).
3. **Per-launch token** (browser mode) — a random secret printed once to the
   server console bootstraps an ``HttpOnly; SameSite=Strict`` session cookie.
   This is the only control that also stops *other local users*: they can open
   the port but cannot guess the token. Jupyter-style; the token never travels
   beyond loopback and no third-party request exists to leak it to.

The middleware is pure ASGI (no NiceGUI dependency) so it is unit-testable
without a server. When no configuration is installed (tests that never call
``run_gui()``), it passes everything through.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field, replace
from http import client as http_client
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qsl, urlencode

from itsdangerous import BadSignature, URLSafeSerializer

SESSION_COOKIE_NAME = "guiskindose_session"
TOKEN_QUERY_PARAM = "token"
DEFAULT_GUI_PORT = 8765

_BAD_HOST_BODY = b"unexpected host"
_FORBIDDEN_BODY = (
    b"forbidden: restart the GUI and open the console URL "
    b"(it carries the launch token)"
)


@dataclass(frozen=True)
class LoopbackSecurityConfig:
    """Per-launch security posture for the GUI server."""

    allowed_hosts: tuple[str, ...] = (
        f"127.0.0.1:{DEFAULT_GUI_PORT}",
        f"localhost:{DEFAULT_GUI_PORT}",
        "127.0.0.1",
        "localhost",
    )
    allowed_origins: tuple[str, ...] = (
        f"http://127.0.0.1:{DEFAULT_GUI_PORT}",
        f"http://localhost:{DEFAULT_GUI_PORT}",
    )
    session_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    launch_token_hash: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    require_token: bool = True

    @classmethod
    def for_port(cls, port: int, *, require_token: bool = True) -> LoopbackSecurityConfig:
        """Build a config scoped to one loopback port (see ``_resolve_port``)."""
        hosts = (f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost")
        origins = tuple(f"http://{host}" for host in hosts[:2])
        return cls(allowed_hosts=hosts, allowed_origins=origins, require_token=require_token)


_CONFIG: LoopbackSecurityConfig | None = None


def configure_loopback_security(config: LoopbackSecurityConfig | None) -> None:
    """Install (or clear, with ``None``) the active loopback security config."""
    global _CONFIG
    _CONFIG = config


def get_loopback_security_config() -> LoopbackSecurityConfig | None:
    """Return the active loopback security config, if any."""
    return _CONFIG


def generate_launch_token(port: int = DEFAULT_GUI_PORT) -> tuple[str, LoopbackSecurityConfig]:
    """Create a fresh per-launch token and its matching port-scoped config.

    Only a SHA-256 hash of the token is kept: the cleartext exists solely in
    the returned string (printed once to the server console) and is compared
    in constant time, so a memory dump of the config alone cannot mint
    sessions.
    """
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).digest()
    return token, replace(LoopbackSecurityConfig.for_port(port), launch_token_hash=digest)


def _headers(scope: dict) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers", []):
        decoded.setdefault(raw_name.decode("latin-1").lower(), raw_value.decode("latin-1"))
    return decoded


def _session_valid(config: LoopbackSecurityConfig, cookie_header: str) -> bool:
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return False
    morsel = cookie.get(SESSION_COOKIE_NAME)
    if morsel is None:
        return False
    serializer = URLSafeSerializer(config.session_secret)
    try:
        return serializer.loads(morsel.value) == {"v": 1}
    except BadSignature:
        return False


def _token_valid(config: LoopbackSecurityConfig, query_string: bytes) -> bool:
    try:
        params = parse_qsl(query_string.decode("ascii"), keep_blank_values=True)
    except (UnicodeDecodeError, ValueError):
        return False
    for name, value in params:
        if name != TOKEN_QUERY_PARAM:
            continue
        # Percent-decoding can yield non-ASCII text from pure-ASCII bytes
        # (e.g. token=%C3%A9); reject it on the 403 path, never hash it.
        if not value.isascii():
            continue
        if hmac.compare_digest(
            hashlib.sha256(value.encode("ascii")).digest(), config.launch_token_hash
        ):
            return True
    return False


def _set_session_cookie(config: LoopbackSecurityConfig) -> bytes:
    serializer = URLSafeSerializer(config.session_secret)
    signed = serializer.dumps({"v": 1})
    return (
        f"{SESSION_COOKIE_NAME}={signed}; Path=/; HttpOnly; SameSite=Strict".encode("ascii")
    )


def _strip_token_param(query_string: bytes) -> bytes:
    # Only called after _token_valid passed on the same bytes, so decoding
    # cannot fail here. Re-encode with urlencode (not string interpolation)
    # so values containing '+' or '%20' round-trip instead of corrupting.
    params = parse_qsl(query_string.decode("ascii"), keep_blank_values=True)
    kept = [(k, v) for k, v in params if k != TOKEN_QUERY_PARAM]
    return urlencode(kept).encode("ascii")


def _redirect_location(scope: dict, rest: bytes) -> bytes:
    # Prefer raw_path (original bytes): re-encoding the decoded path can
    # silently drop characters outside latin-1 on the redirect target.
    raw_path = scope.get("raw_path")
    location = (
        raw_path
        if isinstance(raw_path, bytes) and raw_path
        else (scope.get("path", "/") or "/").encode("utf-8")
    )
    if rest:
        location += b"?" + rest
    return location


def probe_own_server(host: str, port: int, *, timeout: float = 2.0) -> bool:
    """Return True when the listener answers like our middleware.

    A bare ``/`` with no session must come back 403 carrying the exact
    refusal body. Anything else — a foreign service squatting a raced or
    stale port, an error page, silence — means the token URL must not
    auto-open there.
    """
    if host not in ("127.0.0.1", "localhost") or not 1 <= port <= 65535:
        return False
    try:
        connection = http_client.HTTPConnection(host, port, timeout=timeout)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            return response.status == 403 and response.read() == _FORBIDDEN_BODY
        finally:
            connection.close()
    except (OSError, ValueError, http_client.HTTPException):
        return False


async def _respond(send: Any, status: int, body: bytes, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    await send({"type": "http.response.start", "status": status, "headers": headers or []})
    await send({"type": "http.response.body", "body": body})


class LoopbackSecurityMiddleware:
    """Enforce the active :class:`LoopbackSecurityConfig` on ASGI traffic."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        config = _CONFIG
        if config is None or scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        if headers.get("host", "") not in config.allowed_hosts:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4403})
                return
            await _respond(send, 400, _BAD_HOST_BODY)
            return
        origin = headers.get("origin", "")
        if scope["type"] == "websocket":
            # A present-but-foreign Origin is a cross-site page (browsers
            # always send Origin, so it cannot be "missing" for them).
            if origin and origin not in config.allowed_origins:
                await send({"type": "websocket.close", "code": 4403})
                return
            # The session is required whenever tokens are on — even with an
            # allowlisted Origin, which local processes can forge. Native
            # mode (require_token=False) skips this, tolerating embedded
            # webviews that omit the Origin header entirely.
            if config.require_token and not _session_valid(config, headers.get("cookie", "")):
                await send({"type": "websocket.close", "code": 4403})
                return
            await self.app(scope, receive, send)
            return
        if origin and origin not in config.allowed_origins:
            await _respond(send, 403, _FORBIDDEN_BODY)
            return
        if config.require_token and not _session_valid(config, headers.get("cookie", "")):
            if _token_valid(config, scope.get("query_string", b"")):
                rest = _strip_token_param(scope.get("query_string", b""))
                location = _redirect_location(scope, rest)
                await _respond(
                    send,
                    302,
                    b"",
                    [
                        (b"location", location),
                        (b"set-cookie", _set_session_cookie(config)),
                    ],
                )
                return
            await _respond(send, 403, _FORBIDDEN_BODY)
            return
        await self.app(scope, receive, send)
