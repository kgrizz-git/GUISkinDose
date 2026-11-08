"""Static checks for the macOS release signing workflow (no codesign or notary on the runner)."""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
RELEASE_WF = REPO / ".github/workflows/portable-macos-release.yml"
IMPORT_SH = REPO / "packaging/portable/macos_ci_import_signing.sh"
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


def _named_steps(job: dict) -> list[str]:
    return [step["name"] for step in job["steps"] if step.get("name")]


def test_portable_macos_release_triggers_and_environment() -> None:
    wf = _load(RELEASE_WF)
    on = wf.get(True) or wf["on"]
    assert "release" in on
    assert on["release"]["types"] == ["published"]
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
    assert "macos-arm64.zip" in text
    assert "GH_TOKEN: ${{ github.token }}" in text
    assert "macos_verify_developer_id_signing.sh" in text


def test_spike_and_pypi_have_no_release_signing_secrets() -> None:
    spike = SPIKE_WF.read_text(encoding="utf-8")
    pypi = PYPI_WF.read_text(encoding="utf-8")
    assert "macos-release" not in spike
    for name in SECRET_NAMES:
        assert name not in spike
        assert name not in pypi
    assert "macos-release" not in pypi


def test_portable_spike_does_not_set_skip_adhoc_on_default_path() -> None:
    spike = SPIKE_WF.read_text(encoding="utf-8")
    assert "GUISKINDOSE_SKIP_ADHOC_RESIGN" not in spike


def test_sign_macos_step_order_and_conditions() -> None:
    wf = _load(RELEASE_WF)
    steps = wf["jobs"]["sign-macos"]["steps"]
    names = _named_steps(wf["jobs"]["sign-macos"])
    assert names.index("Import signing certificate and notary key") < names.index("Developer ID sign (sign-only)")
    assert names.index("Developer ID sign (sign-only)") < names.index("Verify Developer ID seals after sign")
    assert names.index("Notarize, staple, and write release zip") < names.index("Upload stapled zip and checksum")
    assert names.index("Notarize, staple, and write release zip") < names.index("Attach to GitHub Release")

    upload = next(s for s in steps if s.get("name") == "Upload stapled zip and checksum")
    attach = next(s for s in steps if s.get("name") == "Attach to GitHub Release")
    teardown = next(s for s in steps if s.get("name") == "Restore keychain and delete secrets from disk")
    assert upload.get("if") == "success()"
    assert attach.get("if") is not None
    assert "success()" in attach["if"]
    assert teardown.get("if") == "always()"

    notarize = next(s for s in steps if s.get("name") == "Notarize, staple, and write release zip")
    assert "GUISKINDOSE_NOTARY_KEY" in notarize["env"]
    assert "GUISKINDOSE_NOTARY_KEY_ID" in notarize["env"]
    assert "steps.keychain.outputs.notary_key_path" in notarize["env"]["GUISKINDOSE_NOTARY_KEY"]

    arm64 = next(s for s in steps if s.get("name") == "Require arm64 runner")
    assert names.index("Require arm64 runner") < names.index("Freeze PyInstaller app bundle")
    assert arm64.get("run") == 'test "$(uname -m)" = arm64'


def test_intel_job_has_no_release_attach() -> None:
    wf = _load(RELEASE_WF)
    names = _named_steps(wf["jobs"]["macos-intel-full"])
    assert "Attach to GitHub Release" not in names
    assert "Verify stapled zip expansion" in names
    assert names.index("Notarize, staple, and write release zip") < names.index("Upload stapled zip")


def test_workflow_run_blocks_avoid_inline_expressions() -> None:
    wf = _load(RELEASE_WF)
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run")
            if isinstance(run, str) and "${{" in run:
                pytest.fail(f"run block contains an inline expression in step {step.get('name')!r}")


def test_import_writes_notary_to_outputs_not_env() -> None:
    text = IMPORT_SH.read_text(encoding="utf-8")
    assert "notary_key_path" in text
    assert "notary_key_id" in text
    assert "notary_issuer" in text
    assert "GITHUB_OUTPUT" in text
    assert '>>"$GITHUB_ENV"' not in text
