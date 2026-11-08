"""Static checks for the macOS release signing workflow (no codesign or notary on the runner)."""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
RELEASE_WF = REPO / ".github/workflows/portable-macos-release.yml"
SPIKE_WF = REPO / ".github/workflows/portable-spike.yml"
PYPI_WF = REPO / ".github/workflows/release.yml"

SECRET_NAMES = (
    "DEVELOPER_ID_P12_BASE64",
    "DEVELOPER_ID_P12_PASSWORD",
    "NOTARY_KEY_P8",
    "NOTARY_KEY_ID",
    "NOTARY_ISSUER",
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_portable_macos_release_triggers_and_environment() -> None:
    wf = _load(RELEASE_WF)
    # PyYAML 1.1 parses the workflow key `on:` as boolean True.
    on = wf.get(True) or wf["on"]
    assert "release" in on and on["release"]["types"] == ["published"]
    assert "workflow_dispatch" in on
    assert "pull_request" not in on
    assert "push" not in on

    for job_name in ("sign-macos", "macos-intel-full"):
        job = wf["jobs"][job_name]
        assert job["environment"] == "macos-release"
        perms = job["permissions"]
        assert perms["contents"] == "write"
        assert perms["actions"] == "read"

    matrix_job = wf["jobs"]["sign-macos"]
    checkout = matrix_job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["fetch-depth"] == 0


def test_portable_macos_release_secrets_and_skip_notarize() -> None:
    text = RELEASE_WF.read_text(encoding="utf-8")
    for name in SECRET_NAMES:
        assert f"secrets.{name}" in text
    assert "GUISKINDOSE_SKIP_NOTARIZE" not in text
    assert "GUISKINDOSE_SKIP_ADHOC_RESIGN" in text
    assert "if: success()" in text
    assert "macos-arm64.zip" in text
    assert "GITHUB_SHA" in text and "attach_to_tag" in text
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_spike_and_pypi_have_no_release_signing_secrets() -> None:
    spike = SPIKE_WF.read_text(encoding="utf-8")
    pypi = PYPI_WF.read_text(encoding="utf-8")
    assert "environment:" not in spike or "macos-release" not in spike
    for name in SECRET_NAMES:
        assert name not in spike
        assert name not in pypi
    assert "macos-release" not in pypi


def test_portable_spike_does_not_set_skip_adhoc_on_default_path() -> None:
    spike = SPIKE_WF.read_text(encoding="utf-8")
    assert "GUISKINDOSE_SKIP_ADHOC_RESIGN" not in spike
