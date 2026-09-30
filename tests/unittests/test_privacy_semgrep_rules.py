"""Synthetic regression coverage for the repository privacy Semgrep rules."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_RULES = _ROOT / ".semgrep" / "mypyskindose-privacy.yml"


def _semgrep_tool() -> Any:
    spec = importlib.util.spec_from_file_location("semgrep_tool", _ROOT / "scripts" / "semgrep_tool.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan_environment(root: Path, tool: Any) -> dict[str, str]:
    """Environment for a scan of ``root``, built on the isolated tool's own environment.

    Deliberately ``tool_environment()`` and not ``os.environ.copy()``. `.envrc` exports
    ``UV_PROJECT_ENVIRONMENT=$PWD/.venv`` and ``uv run`` honours it, so a plain copy of the
    environment made this test install semgrep 1.168.0 — with `click 8.1.8`, `mcp 1.23.3`
    and `pyjwt 2.13.0` — straight into the project environment that isolating the scanner
    exists to keep them out of. Verified: the packages appeared in the environment named by
    that variable. It reproduced only where direnv was active, so CI stayed clean.
    """
    environment = tool.tool_environment()
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
            # Keep uv's own cache OUT of the scan root. `XDG_CACHE_HOME` above points
            # into `root` to isolate semgrep's cache, but uvx honours it too, so the
            # isolated tool's unpacked wheels landed inside the directory being scanned
            # and produced nondeterministic findings from third-party source.
            "UV_CACHE_DIR": str(root.parent / "uv-cache"),
        }
    )
    return environment


def _scan(root: Path) -> set[str]:
    # Resolve the same pinned, isolated Semgrep the blocking gate uses, from one module
    # instance so the command and the environment cannot come from different loads of it.
    #
    # No try/except and no skip on purpose: if Semgrep cannot be resolved, letting the
    # SemgrepUnavailableError propagate fails the test, which is the point. The previous
    # `shutil.which` + `pytest.skip` quietly reduced this ruleset's regression coverage to
    # zero the moment semgrep stopped being a dev dependency.
    tool = _semgrep_tool()
    environment = _scan_environment(root, tool)
    completed = subprocess.run(
        [
            *tool.semgrep_argv([]),
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
    target = tmp_path / "src" / "guiskindose" / "gui" / "tabs" / "export.py"
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
    target = tmp_path / "src" / "guiskindose" / "gui" / "tabs" / "export.py"
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


def test_the_scan_never_installs_the_scanner_into_the_project_environment(tmp_path: Path) -> None:
    """Regression test for a leak that only reproduced where direnv was active.

    With `os.environ.copy()` this test ran `uv run` against the project's own
    `UV_PROJECT_ENVIRONMENT`, installing semgrep and its advisory-bearing pins into the
    environment the isolation exists to keep clean.
    """
    environment = _scan_environment(tmp_path, _semgrep_tool())
    target = Path(environment["UV_PROJECT_ENVIRONMENT"])
    assert target != _ROOT / ".venv"
    assert target.is_relative_to(_ROOT / "tools")
    assert "UV_PYTHON" not in environment
