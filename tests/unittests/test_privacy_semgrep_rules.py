"""Synthetic regression coverage for the repository privacy Semgrep rules."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


_RULES = Path(__file__).resolve().parents[2] / ".semgrep" / "mypyskindose-privacy.yml"


def _scan(root: Path) -> set[str]:
    semgrep = shutil.which("semgrep")
    if semgrep is None:
        pytest.skip("semgrep is not installed")
    environment = os.environ.copy()
    cert_file = Path("/etc/ssl/cert.pem")
    if cert_file.is_file():
        environment["SSL_CERT_FILE"] = str(cert_file)
    elif not environment.get("SSL_CERT_FILE"):
        environment.pop("SSL_CERT_FILE", None)
    environment.update(
        {
            "SEMGREP_ENABLE_VERSION_CHECK": "0",
            "SEMGREP_LOG_FILE": str(root / "semgrep.log"),
            "XDG_CACHE_HOME": str(root / ".cache"),
        }
    )
    completed = subprocess.run(
        [
            semgrep,
            "--config",
            str(_RULES),
            "--metrics=off",
            "--json",
            "--quiet",
            ".",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    payload = json.loads(completed.stdout)
    return {str(result["check_id"]).split(".")[-1] for result in payload["results"]}


def test_privacy_rules_detect_representative_leak_sinks(tmp_path: Path) -> None:
    target = tmp_path / "src" / "mypyskindose" / "gui" / "tabs" / "export.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        """
import logging
import tempfile
import traceback

logger = logging.getLogger(__name__)

def unsafe(exc, provenance, filename, output_path):
    logger.exception("export failed")
    logger.error("raw failure: %s", exc)
    logger.warning(f"source={filename}")
    print(f"patient={provenance.patient_id}")
    traceback.print_exc()
    output_path.write_bytes(b"clinical data")
    tempfile.NamedTemporaryFile(delete=False)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert _scan(tmp_path) >= {
        "mypyskindose-filename-var-to-log-or-stdout",
        "mypyskindose-identifier-attr-to-log-or-stdout",
        "mypyskindose-persistent-clinical-named-tempfile",
        "mypyskindose-prohibited-exception-diagnostics",
        "mypyskindose-raw-exception-to-diagnostic",
        "mypyskindose-unsafe-gui-export-write",
    }


def test_privacy_rules_allow_value_safe_helpers(tmp_path: Path) -> None:
    target = tmp_path / "src" / "mypyskindose" / "gui" / "tabs" / "export.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        """
def safe(exc, logger, output_path, payload):
    safe_error_event(logger, "report_export", exc)
    message = f"error_type={exception_class_name(exc)}"
    atomic_write_private(output_path, payload)
    return message
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert _scan(tmp_path) == set()
