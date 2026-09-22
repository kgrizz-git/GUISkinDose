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
2. **Origin validation** — websocket handshakes must carry an allowlisted
   loopback ``Origin`` (browsers always send one); HTTP requests carrying an
   ``Origin`` must also match. Cross-site drive-by traffic is rejected.
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
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import parse_qsl

from itsdangerous import BadSignature, URLSafeSerializer

SESSION_COOKIE_NAME = "guiskindose_session"
TOKEN_QUERY_PARAM = "token"

_BAD_HOST_BODY = b"unexpected host"
_FORBIDDEN_BODY = (
    b"forbidden: restart the GUI and open the console URL "
    b"(it carries a one-time launch token)"
)


@dataclass(frozen=True)
class LoopbackSecurityConfig:
    """Per-launch security posture for the GUI server."""

    allowed_hosts: tuple[str, ...] = ("127.0.0.1:8765", "localhost:8765", "127.0.0.1", "localhost")
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:8765", "http://localhost:8765")
    session_secret: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    launch_token_hash: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    require_token: bool = True


_CONFIG: LoopbackSecurityConfig | None = None


def configure_loopback_security(config: LoopbackSecurityConfig | None) -> None:
    """Install (or clear, with ``None``) the active loopback security config."""
    global _CONFIG
    _CONFIG = config


def get_loopback_security_config() -> LoopbackSecurityConfig | None:
    """Return the active loopback security config, if any."""
    return _CONFIG


def generate_launch_token() -> tuple[str, LoopbackSecurityConfig]:
    """Create a fresh per-launch token and its matching config.

    Only a SHA-256 hash of the token is kept: the cleartext exists solely in
    the returned string (printed once to the server console) and is compared
    in constant time, so a memory dump of the config alone cannot mint
    sessions.
    """
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).digest()
    return token, LoopbackSecurityConfig(launch_token_hash=digest)


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
    # cannot fail here.
    params = parse_qsl(query_string.decode("ascii"), keep_blank_values=True)
    kept = [(k, v) for k, v in params if k != TOKEN_QUERY_PARAM]
    return "&".join(f"{k}={v}" for k, v in kept).encode("ascii")


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
            if origin not in config.allowed_origins:
                await send({"type": "websocket.close", "code": 4403})
                return
            await self.app(scope, receive, send)
            return
        if origin and origin not in config.allowed_origins:
            await _respond(send, 403, _FORBIDDEN_BODY)
            return
        if config.require_token and not _session_valid(config, headers.get("cookie", "")):
            if _token_valid(config, scope.get("query_string", b"")):
                path = scope.get("path", "/") or "/"
                location = path.encode("latin-1", "ignore")
                rest = _strip_token_param(scope.get("query_string", b""))
                if rest:
                    location += b"?" + rest
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
