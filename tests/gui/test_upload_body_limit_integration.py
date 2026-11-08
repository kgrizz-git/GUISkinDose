"""Upload body cap against a real Starlette multipart parser.

Lives under tests/gui because Starlette ships with the GUI extra.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("starlette")

from starlette.applications import Starlette
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.types import Message, Scope

from guiskindose.gui.upload_body_limit_middleware import (
    MAX_GUI_UPLOAD_BODY_BYTES,
    UploadBodyLimitMiddleware,
)

_BOUNDARY = "testboundary"


def _upload_app(received: list[str]) -> Starlette:
    """Build an app shaped like NiceGUI's upload route: parse the form, then run the callback."""

    async def upload(request: Request) -> PlainTextResponse:
        """Parse the multipart body and record each file the callback would see."""
        async with request.form() as form:
            for value in form.values():
                if isinstance(value, UploadFile):
                    received.append(str(value.filename))
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/_nicegui/client/c1/upload/e1", upload, methods=["POST"])])
    app.add_middleware(UploadBodyLimitMiddleware)
    return app


def _multipart_chunks() -> list[bytes]:
    """A valid small file part, then a second part whose data runs past the cap."""
    first = (
        f"--{_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="file"; filename="pack.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
        "small\r\n"
        f"--{_BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="file"; filename="big.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
    ).encode()
    filler = b"x" * (4 * 1024 * 1024)
    chunks = [first]
    total = len(first)
    while total <= MAX_GUI_UPLOAD_BODY_BYTES:
        chunks.append(filler)
        total += len(filler)
    chunks.append(f"\r\n--{_BOUNDARY}--\r\n".encode())
    return chunks


def test_oversized_multipart_upload_gets_413_and_no_callback() -> None:
    """A streamed upload past the cap gets one 413, and the callback never sees a file."""
    received: list[str] = []
    app = _upload_app(received)
    messages: list[Message] = []

    async def _exercise() -> None:
        """Drive the ASGI app with a chunked body that has no Content-Length."""
        chunks = _multipart_chunks()

        async def receive() -> Message:
            """Return the next body chunk."""
            body = chunks.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(chunks)}

        async def send(message: Message) -> None:
            """Record a response message."""
            messages.append(message)

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/_nicegui/client/c1/upload/e1",
            "raw_path": b"/_nicegui/client/c1/upload/e1",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", f"multipart/form-data; boundary={_BOUNDARY}".encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8765),
        }
        await app(scope, receive, send)

    asyncio.run(_exercise())
    statuses = [m["status"] for m in messages if m["type"] == "http.response.start"]
    assert statuses == [413]
    assert received == []
