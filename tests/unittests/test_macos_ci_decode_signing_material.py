"""Decode helpers for macOS CI signing material (no real secrets)."""

import base64
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DECODE = REPO / "packaging/portable/macos_ci_decode_signing_material.py"


def test_notary_key_accepts_pem_or_base64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEI\n-----END PRIVATE KEY-----\n"
    b64 = base64.b64encode(pem.encode()).decode()
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    for raw in (pem, b64):
        monkeypatch.setenv("NOTARY_KEY_P8", raw)
        out = tmp_path / "AuthKey.p8"
        out.unlink(missing_ok=True)
        subprocess.run([sys.executable, str(DECODE), "notary"], check=True)
        assert out.is_file()
        assert stat.S_IMODE(out.stat().st_mode) == 0o600
        assert "BEGIN PRIVATE KEY" in out.read_text(encoding="utf-8")


def test_notary_wrapped_base64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pem = "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEEI\n-----END EC PRIVATE KEY-----\n"
    wrapped = "\n".join(base64.b64encode(pem.encode()).decode()[i : i + 24] for i in range(0, 40, 24))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("NOTARY_KEY_P8", wrapped)
    (tmp_path / "AuthKey.p8").unlink(missing_ok=True)
    subprocess.run([sys.executable, str(DECODE), "notary"], check=True)


def test_p12_accepts_wrapped_base64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"\x30\x82" + b"x" * 32
    encoded = base64.b64encode(payload).decode()
    wrapped = "\n".join(encoded[i : i + 30] for i in range(0, len(encoded), 30))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("DEVELOPER_ID_P12_BASE64", wrapped)
    out = tmp_path / "developer-id.p12"
    out.unlink(missing_ok=True)
    subprocess.run([sys.executable, str(DECODE), "p12"], check=True)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert out.read_bytes() == payload


def test_notary_rejects_non_pem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("NOTARY_KEY_P8", "definitely-not-pem-or-key")
    code = subprocess.run([sys.executable, str(DECODE), "notary"]).returncode
    assert code != 0
