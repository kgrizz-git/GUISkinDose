"""Regression tests for the untrusted-PR scanner boundary in CI."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github/workflows/ci.yml"


def job_section(workflow: str, job: str, next_job: str) -> str:
    """Return one top-level workflow job section from the checked-in workflow."""
    return workflow.split(f"  {job}:\n", maxsplit=1)[1].split(f"  {next_job}:\n", maxsplit=1)[0]


def test_tokenized_sonar_is_opt_in_and_never_runs_on_pr_heads() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    sonar = job_section(workflow, "sonar-scan", "gitleaks")

    assert "github.event_name == 'push'" in sonar
    assert "github.ref == 'refs/heads/main'" in sonar
    assert "vars.SONAR_PROTECTED_MAIN_ENABLED == 'true'" in sonar
    assert "github.event_name == 'pull_request'" not in sonar
    assert "SONAR_TOKEN_AVAILABLE: ${{ secrets.SONAR_TOKEN != '' }}" in sonar
    assert "if: env.SONAR_TOKEN_AVAILABLE == 'true'" in sonar
    assert "SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}" in sonar
    # A red Quality Gate must fail the job so ci-issue-notify files a tracking issue.
    assert "-Dsonar.qualitygate.wait=true" in sonar


def test_ci_does_not_post_dead_coderabbit_review_requests() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "request-coderabbit:" not in workflow
    assert "@coderabbitai review" not in workflow
    assert "coderabbit-privacy-gate:" not in workflow


def test_no_workflow_uses_privileged_pull_request_target() -> None:
    for workflow_path in (REPO_ROOT / ".github/workflows").glob("*.yml"):
        assert "pull_request_target" not in workflow_path.read_text(encoding="utf-8")
