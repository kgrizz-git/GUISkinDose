"""Static checks for the macOS release signing workflow (no codesign or notary on the runner)."""

import os
import shutil
import subprocess
import sys
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
        assert wf["jobs"][job_name]["environment"] == "macos-release"

    arm_perms = wf["jobs"]["sign-macos"]["permissions"]
    assert arm_perms["contents"] == "write"
    assert arm_perms["actions"] == "read"
    intel_perms = wf["jobs"]["macos-intel-full"]["permissions"]
    assert intel_perms["contents"] == "read"
    assert intel_perms["actions"] == "read"

    matrix_job = wf["jobs"]["sign-macos"]
    checkout = matrix_job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["fetch-depth"] == 0


DISPATCH_GATE = "Require dispatch from main or a v* tag"


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="runs the gate under bash")
@pytest.mark.parametrize("job_name", ["sign-macos", "macos-intel-full"])
@pytest.mark.parametrize(
    ("ref", "admitted"),
    [
        ("refs/heads/main", True),
        ("refs/tags/v1.2.3", True),
        ("refs/tags/v1.2.3-rc.1", True),
        ("refs/heads/feature", False),
        ("refs/tags/foo", False),
        ("refs/tags/V1.2.3", False),
        ("refs/tags/v", False),
        ("refs/pull/12/merge", False),
        ("", False),
    ],
)
def test_dispatch_gate_admits_main_and_version_tags(job_name: str, ref: str, admitted: bool) -> None:
    wf = _load(RELEASE_WF)
    gate = next(s for s in wf["jobs"][job_name]["steps"] if s.get("name") == DISPATCH_GATE)
    assert gate["if"] == "github.event_name == 'workflow_dispatch'"
    assert gate["env"]["WORKFLOW_REF"] == "${{ github.ref }}"
    proc = subprocess.run(
        ["bash", "-c", gate["run"]],
        env={"WORKFLOW_REF": ref, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        check=False,
    )
    assert (proc.returncode == 0) is admitted


TAG_GATE = "Require attach tag commit matches checkout"


# Ignore the developer's global and system git config, so tag or commit signing cannot prompt or hang.
_HERMETIC_GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_HERMETIC_GIT_ENV,
        stdin=subprocess.DEVNULL,
        timeout=30,
    ).stdout.strip()


@pytest.fixture
def two_commit_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """A repo whose v1.0.0 tag points at the first of two commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for n in (1, 2):
        (repo / "f.txt").write_text(str(n), encoding="utf-8")
        _git(repo, "add", "f.txt")
        _git(repo, "-c", "user.name=t", "-c", "user.email=test", "commit", "-q", "-m", f"c{n}")
        if n == 1:
            _git(repo, "tag", "v1.0.0")
    return repo, _git(repo, "rev-parse", "HEAD~1"), _git(repo, "rev-parse", "HEAD")


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None or shutil.which("git") is None,
    reason="runs the gate under bash against a scratch git repo",
)
@pytest.mark.parametrize(
    ("tag", "checkout", "admitted"),
    [
        ("v1.0.0", "tagged", True),
        ("v1.0.0", "later", False),
        ("v9.9.9", "tagged", False),
        ("not-a-tag", "tagged", False),
    ],
)
def test_attach_tag_gate_requires_matching_commit(
    two_commit_repo: tuple[Path, str, str], tag: str, checkout: str, admitted: bool
) -> None:
    repo, tagged, later = two_commit_repo
    wf = _load(RELEASE_WF)
    gate = next(s for s in wf["jobs"]["sign-macos"]["steps"] if s.get("name") == TAG_GATE)
    assert gate["env"]["ATTACH_TO_TAG"] == "${{ inputs.attach_to_tag }}"
    proc = subprocess.run(
        ["bash", "-c", gate["run"]],
        cwd=repo,
        env={
            "ATTACH_TO_TAG": tag,
            "GITHUB_SHA": tagged if checkout == "tagged" else later,
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        },
        stdin=subprocess.DEVNULL,
        timeout=30,
        capture_output=True,
        check=False,
    )
    assert (proc.returncode == 0) is admitted


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
