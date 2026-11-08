"""ASGI middleware capping NiceGUI upload POST bodies (defense in depth).

Client-side ``max_file_size`` on ``ui.upload`` is not enforced server-side. The
largest widget cap in the GUI is the 80 MiB phantom pack upload; RDSR/tabular
uploads use 64 MiB. Reject bodies above that ceiling plus multipart overhead.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

# Largest ``ui.upload`` cap in the app (phantom pack) plus multipart padding.
_PHANTOM_PACK_UPLOAD_BYTES = 80 * 1024 * 1024
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MAX_GUI_UPLOAD_BODY_BYTES = _PHANTOM_PACK_UPLOAD_BYTES + _MULTIPART_OVERHEAD_BYTES

_UPLOAD_PATH = re.compile(r"/_nicegui/.*upload", re.IGNORECASE)


async def _reject_413(send: Callable[..., Awaitable[None]]) -> None:
    """Reject 413."""
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": b"Upload too large.", "more_body": False})


def _declared_length_too_large(scope: dict) -> bool:
    """True when Content-Length is over the cap or is not a number."""
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    content_length = headers.get("content-length")
    if content_length is None:
        return False
    try:
        return int(content_length) > MAX_GUI_UPLOAD_BODY_BYTES
    except ValueError:
        return True


class UploadBodyLimitMiddleware:
    """Reject oversized bodies on NiceGUI upload routes before handlers run."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        """Initialize the instance."""
        self.app = app

    async def __call__(self, scope: dict, receive: Callable[..., Awaitable[dict]], send: Callable) -> None:
        """Invoke the callable."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "").upper()
        path = scope.get("path", "")
        if method != "POST" or not _UPLOAD_PATH.search(path):
            await self.app(scope, receive, send)
            return
        if _declared_length_too_large(scope):
            await _reject_413(send)
            return
        seen = 0
        rejected = False

        async def capped_receive() -> dict:
            """Count streamed body bytes and send a 413 once the cap is passed."""
            nonlocal seen, rejected
            message = await receive()
            if message["type"] == "http.request" and not rejected:
                seen += len(message.get("body", b""))
                if seen > MAX_GUI_UPLOAD_BODY_BYTES:
                    rejected = True
                    await _reject_413(send)
                    # Ending the body makes the handler stop reading.
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message: dict) -> None:
            """Drop the handler's own response after the 413 has gone out."""
            if not rejected:
                await send(message)

        await self.app(scope, capped_receive, guarded_send)
