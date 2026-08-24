"""Unit tests for scripts/check_licenses.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_licenses.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_licenses", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licenses"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cl():
    return _load_module()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("MIT License", "MIT"),
        ("Apache License 2.0", "Apache-2.0"),
        ("BSD License", "BSD-3-Clause"),
        ("GNU General Public License v3 (GPLv3)", "GPL-3.0-or-later"),
        ("GPL licensed project", "GPL-2.0-or-later"),
        ("GNU Affero General Public License", "AGPL-3.0-or-later"),
        ("unrecognised proprietary terms", "UNKNOWN"),
        ("", "UNKNOWN"),
    ],
)
def test_normalize_token(cl, raw, expected):
    assert cl._normalize_token(raw) == expected


def test_license_from_classifiers(cl):
    classifiers = [
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
    ]
    assert cl._license_from_classifiers(classifiers) == ["MIT"]


def test_evaluate_packages_forbidden(cl):
    pkg = cl.PackageLicense(
        name="copyleft-lib",
        version="1.0.0",
        license_ids=("GPL-3.0-or-later",),
        raw_license="GPLv3",
        home_page="",
    )
    forbidden, unknown, review = cl.evaluate_packages([pkg], strict=False)
    assert forbidden == [pkg]
    assert unknown == []
    assert review == []


def test_dual_license_or_allowed(cl):
    pkg = cl.PackageLicense(
        name="docutils",
        version="0.23",
        license_ids=("BSD-3-Clause", "GPL-2.0-or-later"),
        raw_license="BSD-2-Clause OR GPL-2.0-or-later",
        home_page="",
        license_operator="OR",
    )
    forbidden, unknown, review = cl.evaluate_packages([pkg], strict=False)
    assert forbidden == []
    assert unknown == []
    assert review == []
    assert pkg.status == "allowed"


def test_evaluate_packages_unknown_strict(cl):
    pkg = cl.PackageLicense(
        name="mystery-lib",
        version="0.1.0",
        license_ids=("UNKNOWN",),
        raw_license="",
        home_page="",
    )
    forbidden, unknown, _review = cl.evaluate_packages([pkg], strict=True)
    assert forbidden == []
    assert unknown == [pkg]


def test_render_notices_includes_header(cl):
    pkg = cl.PackageLicense(
        name="example",
        version="1.2.3",
        license_ids=("MIT",),
        raw_license="MIT",
        home_page="https://example.com",
    )
    text = cl.render_notices([pkg], ROOT)
    assert "# Third-party notices" in text
    assert "| example | 1.2.3 | MIT |" in text


def test_check_notices_detects_stale_file(cl, tmp_path):
    notices = tmp_path / "dev-docs" / "THIRD_PARTY_NOTICES.md"
    notices.parent.mkdir(parents=True)
    notices.write_text("# stale\n", encoding="utf-8")

    original_path = cl.NOTICES_PATH
    cl.NOTICES_PATH = Path("dev-docs/THIRD_PARTY_NOTICES.md")
    try:
        exit_code = cl.check_licenses(tmp_path, check_notices=True)
    finally:
        cl.NOTICES_PATH = original_path

    assert exit_code == 1


def test_check_notices_missing_file_reports_locked_command(cl, tmp_path, capsys):
    exit_code = cl.check_licenses(tmp_path, check_notices=True)

    assert exit_code == 1
    assert f"Run: {cl.LOCKED_LICENSE_COMMAND} --write-notices" in capsys.readouterr().err
