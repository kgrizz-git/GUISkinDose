"""Decode GitHub environment signing material to mode-600 files under RUNNER_TEMP."""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

RUNNER_TEMP = Path(os.environ["RUNNER_TEMP"])


def _write_exclusive_bytes(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def _write_exclusive_text(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_p12() -> None:
    raw = "".join(os.environ["DEVELOPER_ID_P12_BASE64"].split())
    try:
        payload = base64.b64decode(raw, validate=True)
    except Exception:
        raise SystemExit(1) from None
    _write_exclusive_bytes(RUNNER_TEMP / "developer-id.p12", payload)


def write_notary_p8() -> None:
    raw = os.environ["NOTARY_KEY_P8"].strip()
    if "BEGIN" in raw:
        text = raw
    else:
        compact = "".join(raw.split())
        try:
            text = base64.b64decode(compact).decode("utf-8")
        except Exception:
            raise SystemExit(1) from None
    if "BEGIN PRIVATE KEY" not in text and "BEGIN EC PRIVATE KEY" not in text:
        raise SystemExit(1)
    _write_exclusive_text(RUNNER_TEMP / "AuthKey.p8", text)


def main() -> None:
    mode = sys.argv[1]
    if mode == "p12":
        write_p12()
    elif mode == "notary":
        write_notary_p8()
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
