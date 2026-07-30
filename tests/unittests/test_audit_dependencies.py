"""Unit tests for scripts/audit_dependencies.py."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_dependencies.py"
UV_AUDIT_VERSION = "uv 0.11.19"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_dependencies", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_dependencies"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ad():
    return _load_module()


def test_main_uv_audit_success(ad):
    """Test standard uv audit path returning success."""
    # Pin CI falsy so the local --frozen branch is exercised deterministically
    # regardless of whether the test itself runs under CI (which sets CI=true).
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch.dict(os.environ, {"CI": ""}), \
         patch("sys.argv", ["audit_dependencies.py"]), \
         patch("subprocess.run") as mock_run:
         
        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "--version" in cmd:
                res.stdout = UV_AUDIT_VERSION
            elif "audit" in cmd and "--help" in cmd:
                res.stdout = "uv audit help"
            return res
            
        mock_run.side_effect = mock_run_impl

        code = ad.main()

        assert code == 0
        called_cmd = mock_run.call_args_list[-1][0][0]
        assert called_cmd[0] == "/path/to/uv"
        assert called_cmd[1] == "audit"
        assert "--frozen" in called_cmd


def test_main_uv_missing_fallback(ad):
    """Test fallback to pip-audit when uv is missing."""
    with patch("shutil.which", return_value=None), \
         patch("subprocess.run") as mock_run:
        
        mock_audit = MagicMock()
        mock_audit.returncode = 0
        mock_run.return_value = mock_audit

        code = ad.main([])

        assert code == 0
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "pip-audit"


def test_main_uv_lock_missing_fallback(ad):
    """Test fallback to pip-audit when uv.lock is missing."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=False), \
         patch("subprocess.run") as mock_run:
        
        mock_audit = MagicMock()
        mock_audit.returncode = 0
        mock_run.return_value = mock_audit

        code = ad.main([])

        assert code == 0
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "pip-audit"


def test_main_uv_audit_unsupported_fallback(ad):
    """Test fallback when uv is present but does not support uv audit."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run") as mock_run:
         
        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            if "--version" in cmd:
                res.returncode = 0
                res.stdout = UV_AUDIT_VERSION
            elif "audit" in cmd and "--help" in cmd:
                res.returncode = 1
                res.stdout = ""
            else:
                res.returncode = 0
                res.stdout = ""
            return res
            
        mock_run.side_effect = mock_run_impl

        code = ad.main([])

        assert code == 0
        called_cmd = mock_run.call_args_list[-1][0][0]
        assert called_cmd[0] == "pip-audit"


def test_main_uv_too_old_fallback(ad):
    """Test fallback when uv version is too old (< 0.11.19)."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run") as mock_run:
        
        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            if "--version" in cmd:
                res.returncode = 0
                res.stdout = "uv 0.11.18"
            else:
                res.returncode = 0
                res.stdout = ""
            return res
            
        mock_run.side_effect = mock_run_impl

        code = ad.main([])

        assert code == 0
        called_cmd = mock_run.call_args_list[-1][0][0]
        assert called_cmd[0] == "pip-audit"


def test_build_uv_audit_argv_allowlist(ad):
    """Only --frozen / --locked survive the trusted argv rebuild."""
    assert ad.build_uv_audit_argv("/path/to/uv", []) == ["/path/to/uv", "audit"]
    assert ad.build_uv_audit_argv("/path/to/uv", ["--frozen"]) == [
        "/path/to/uv",
        "audit",
        "--frozen",
    ]
    assert ad.build_uv_audit_argv("/path/to/uv", ["--locked"]) == [
        "/path/to/uv",
        "audit",
        "--locked",
    ]
    # pip-audit-only flags are stripped; allowlisted flags remain.
    assert ad.build_uv_audit_argv("/path/to/uv", ["--desc", "on", "--frozen"]) == [
        "/path/to/uv",
        "audit",
        "--frozen",
    ]


def test_build_uv_audit_argv_rejects_unknown(ad):
    """Non-allowlisted tokens (including --ignore) must raise ValueError."""
    with pytest.raises(ValueError, match="unsupported or unsafe"):
        ad.build_uv_audit_argv("/path/to/uv", ["--ignore", "GHSA-1"])
    with pytest.raises(ValueError, match="unsupported or unsafe"):
        ad.build_uv_audit_argv("/path/to/uv", ["--frozen", "evil"])
    with pytest.raises(ValueError, match="unsupported or unsafe"):
        ad.build_uv_audit_argv("/path/to/uv", ["--frozen\n"])


def test_main_flag_filtering(ad):
    """pip-audit-only flags are stripped; leftover non-allowlisted args fail closed."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch.dict(os.environ, {"CI": ""}), \
         patch("subprocess.run") as mock_run, \
         patch("sys.argv", ["audit_dependencies.py", "--desc", "on", "--format", "json", "--ignore", "GHSA-1"]):

        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "--version" in cmd:
                res.stdout = UV_AUDIT_VERSION
            elif "audit" in cmd and "--help" in cmd:
                res.stdout = "uv audit help"
            return res

        mock_run.side_effect = mock_run_impl

        with pytest.raises(ValueError, match="unsupported or unsafe"):
            ad.main()


def test_main_allowlisted_passthrough(ad):
    """Explicit --frozen from argv is accepted on the uv audit path."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch.dict(os.environ, {"CI": ""}), \
         patch("subprocess.run") as mock_run, \
         patch("sys.argv", ["audit_dependencies.py", "--desc", "on", "--frozen"]):

        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "--version" in cmd:
                res.stdout = UV_AUDIT_VERSION
            elif "audit" in cmd and "--help" in cmd:
                res.stdout = "uv audit help"
            return res

        mock_run.side_effect = mock_run_impl

        code = ad.main()

        assert code == 0
        called_cmd = mock_run.call_args_list[-1][0][0]
        assert called_cmd == ["/path/to/uv", "audit", "--frozen"]


def test_main_ci_enforcement(ad):
    """Test that --locked is appended in CI environment."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("sys.argv", ["audit_dependencies.py"]), \
         patch.dict(os.environ, {"CI": "true"}):
          
        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            if "--version" in cmd:
                res.stdout = UV_AUDIT_VERSION
            elif "audit" in cmd and "--help" in cmd:
                res.stdout = "uv audit help"
            return res
            
        mock_run.side_effect = mock_run_impl

        code = ad.main()

        assert code == 0
        called_cmd = mock_run.call_args_list[-1][0][0]
        assert called_cmd[0] == "/path/to/uv"
        assert called_cmd[1] == "audit"
        assert "--locked" in called_cmd
        assert "--frozen" not in called_cmd


def test_main_uv_audit_exec_filenotfound_fallback(ad):
    """Test that if executing the uv binary fails with FileNotFoundError, it falls back to pip-audit."""
    with patch("shutil.which", return_value="/path/to/uv"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("sys.argv", ["audit_dependencies.py"]), \
         patch("subprocess.run") as mock_run:
         
        def mock_run_impl(cmd, *args, **kwargs):
            res = MagicMock()
            if "--version" in cmd:
                res.returncode = 0
                res.stdout = UV_AUDIT_VERSION
            elif "audit" in cmd and "--help" in cmd:
                res.returncode = 0
                res.stdout = "uv audit help"
            elif "audit" in cmd:
                raise FileNotFoundError()
            else:
                res.returncode = 0
                res.stdout = ""
            return res
            
        mock_run.side_effect = mock_run_impl

        code = ad.main()

        # The exit code should be 0 from the successful fallback to pip-audit
        assert code == 0
        called_cmd = mock_run.call_args_list[-1][0][0]
        assert called_cmd[0] == "pip-audit"


def test_load_audit_ignores_reads_pyproject(ad):
    """[tool.uv.audit] ignore lists should load as a flat list of advisory IDs."""
    pytest.importorskip("tomllib")
    ids = ad._load_audit_ignores(ROOT)
    assert isinstance(ids, list)
    assert all(isinstance(v, str) for v in ids)


def test_pip_audit_fallback_mirrors_tracked_ignores(ad):
    """The pip-audit fallback should inject --ignore-vuln for each tracked suppression."""
    with patch("shutil.which", return_value=None), \
         patch.object(ad, "_load_audit_ignores", return_value=["GHSA-TEST-0001"]), \
         patch("subprocess.run") as mock_run:

        mock_audit = MagicMock()
        mock_audit.returncode = 0
        mock_run.return_value = mock_audit

        code = ad.main([])

        assert code == 0
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "pip-audit"
        assert "--ignore-vuln" in called_cmd
        assert "GHSA-TEST-0001" in called_cmd
        # flag and value should be adjacent
        idx = called_cmd.index("--ignore-vuln")
        assert called_cmd[idx + 1] == "GHSA-TEST-0001"


def test_pip_audit_validation_rejects_unknown(ad):
    """Non-allowlisted tokens (including --ignore) must raise ValueError on pip-audit fallback path."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(ValueError, match="unsupported or unsafe"):
            ad.main(["--unknown-flag"])


def test_main_pip_audit_missing_error(ad):
    """Test that if pip-audit is missing, FileNotFoundError is caught, prints error, and exits with 1."""
    with patch("shutil.which", return_value=None), \
         patch("subprocess.run", side_effect=FileNotFoundError):

        code = ad.main([])

        assert code == 1
