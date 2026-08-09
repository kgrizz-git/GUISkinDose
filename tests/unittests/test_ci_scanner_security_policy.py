"""Regression tests for the untrusted-PR scanner boundary in CI."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"


def job_section(workflow: str, job: str, next_job: str) -> str:
    """Return one top-level workflow job section from the checked-in workflow."""
    return workflow.split(f"  {job}:\n", maxsplit=1)[1].split(f"  {next_job}:\n", maxsplit=1)[0]


def test_tokenized_sonar_is_opt_in_and_never_runs_on_pr_heads() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    sonar = job_section(workflow, "sonar-scan", "cloud-scans-main")

    assert "github.event_name == 'push'" in sonar
    assert "github.ref == 'refs/heads/main'" in sonar
    assert "vars.SONAR_PROTECTED_MAIN_ENABLED == 'true'" in sonar
    assert "github.event_name == 'pull_request'" not in sonar
    assert "SONAR_TOKEN_AVAILABLE: ${{ secrets.SONAR_TOKEN != '' }}" in sonar
    assert "if: env.SONAR_TOKEN_AVAILABLE == 'true'" in sonar
    assert "SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}" in sonar


def test_coderabbit_remains_requested_only_after_the_privacy_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coderabbit = job_section(workflow, "request-coderabbit", "static-analysis")

    assert "types: [opened, synchronize, reopened, ready_for_review]" in workflow
    assert "needs: [schedule-gate, privacy-gates]" in coderabbit
    assert "github.event_name == 'pull_request'" in coderabbit
    assert "github.event.pull_request.head.repo.full_name == github.repository" in coderabbit
    assert "github.event.pull_request.draft == false" not in coderabbit
    assert "actions/github-script@3a2844b7e9c422d3c10d287c895573f7108da1b3  # v9" in coderabbit
    assert "@coderabbitai review" in coderabbit
    assert "Privacy gate passed for ${context.payload.pull_request.head.sha}." in coderabbit
    assert "<!-- coderabbit-privacy-gate:${context.payload.pull_request.head.sha} -->" in coderabbit
    assert "comment.user?.login === 'github-actions[bot]' && comment.body?.includes(marker)" in coderabbit


def test_no_workflow_uses_privileged_pull_request_target() -> None:
    for workflow_path in (REPO_ROOT / ".github/workflows").glob("*.yml"):
        assert "pull_request_target" not in workflow_path.read_text(encoding="utf-8")
