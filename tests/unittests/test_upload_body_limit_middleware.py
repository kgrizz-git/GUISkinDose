"""ASGI upload body limit middleware."""

from __future__ import annotations

import asyncio

from guiskindose.gui.upload_body_limit_middleware import MAX_GUI_UPLOAD_BODY_BYTES, UploadBodyLimitMiddleware


async def _noop_app(scope, receive, send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


def test_rejects_oversized_content_length() -> None:
    async def _exercise() -> list[dict]:
        middleware = UploadBodyLimitMiddleware(_noop_app)
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/_nicegui/upload/abc",
            "headers": [(b"content-length", str(MAX_GUI_UPLOAD_BODY_BYTES + 1).encode())],
        }

        async def receive() -> dict:
            return {"type": "http.request", "body": b"", "more_body": False}

        await middleware(scope, receive, send)
        return messages

    messages = asyncio.run(_exercise())
    assert messages[0]["status"] == 413


def test_streamed_overflow_sends_a_single_413() -> None:
    """A body without Content-Length that passes the cap gets one 413 and no handler response."""

    async def _reading_app(scope, receive, send) -> None:
        """Read the whole body, then answer 200 as a real handler would."""
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    async def _exercise() -> list[dict]:
        """Stream two chunks whose total passes the cap."""
        middleware = UploadBodyLimitMiddleware(_reading_app)
        messages: list[dict] = []
        chunk = b"x" * (MAX_GUI_UPLOAD_BODY_BYTES // 2 + 1)
        queue = [
            {"type": "http.request", "body": chunk, "more_body": True},
            {"type": "http.request", "body": chunk, "more_body": True},
            {"type": "http.request", "body": b"", "more_body": False},
        ]

        async def receive() -> dict:
            """Return the next queued body message."""
            return queue.pop(0)

        async def send(message: dict) -> None:
            """Record a response message."""
            messages.append(message)

        scope = {"type": "http", "method": "POST", "path": "/_nicegui/upload/abc", "headers": []}
        await middleware(scope, receive, send)
        return messages

    messages = asyncio.run(_exercise())
    starts = [m for m in messages if m["type"] == "http.response.start"]
    assert [m["status"] for m in starts] == [413]
