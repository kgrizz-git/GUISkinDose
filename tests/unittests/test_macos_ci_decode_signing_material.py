"""Decode helpers for macOS CI signing material (no real secrets)."""

import base64
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECODE = REPO / "packaging/portable/macos_ci_decode_signing_material.py"


def test_notary_key_accepts_pem_or_base64(tmp_path: Path, monkeypatch) -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nMC4CAQAwBQYDK2VwBCIEI\n-----END PRIVATE KEY-----\n"
    b64 = base64.b64encode(pem.encode()).decode()
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    for raw in (pem, b64):
        monkeypatch.setenv("NOTARY_KEY_P8", raw)
        out = tmp_path / "AuthKey.p8"
        out.unlink(missing_ok=True)
        subprocess.run([sys.executable, str(DECODE), "notary"], check=True)
        assert out.is_file()
        assert "BEGIN PRIVATE KEY" in out.read_text(encoding="utf-8")
