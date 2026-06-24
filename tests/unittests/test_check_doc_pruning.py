"""Unit tests for scripts/check_doc_pruning.py."""

from pathlib import Path

from scripts.check_doc_pruning import GitAge, collect_pruning_candidates, iter_prunable_docs


def test_iter_prunable_docs_skips_master_plans(tmp_path: Path) -> None:
    repo_root = tmp_path
    plans = repo_root / "dev-docs" / "plans"
    assessments = repo_root / "dev-docs" / "assessments"
    plans.mkdir(parents=True)
    assessments.mkdir(parents=True)
    (plans / "GUI_PLAN.md").write_text("# master\n", encoding="utf-8")
    (plans / "small-execution.md").write_text("# execution\n", encoding="utf-8")
    (assessments / "REVIEW.md").write_text("# review\n", encoding="utf-8")

    docs = [(path.relative_to(repo_root).as_posix(), category) for path, category, _ in iter_prunable_docs(repo_root)]

    assert ("dev-docs/plans/GUI_PLAN.md", "active execution plan") not in docs
    assert ("dev-docs/plans/small-execution.md", "active execution plan") in docs
    assert ("dev-docs/assessments/REVIEW.md", "assessment") in docs


def test_collect_pruning_candidates_requires_days_and_commits(tmp_path: Path) -> None:
    repo_root = tmp_path
    plans = repo_root / "dev-docs" / "plans"
    plans.mkdir(parents=True)
    (plans / "old-plan.md").write_text("# old\n", encoding="utf-8")
    (plans / "recent-plan.md").write_text("# recent\n", encoding="utf-8")
    (plans / "low-commit-plan.md").write_text("# low commit\n", encoding="utf-8")

    ages = {
        "dev-docs/plans/old-plan.md": GitAge(days_since_touch=31, commits_since_touch=11),
        "dev-docs/plans/recent-plan.md": GitAge(days_since_touch=2, commits_since_touch=12),
        "dev-docs/plans/low-commit-plan.md": GitAge(days_since_touch=31, commits_since_touch=2),
    }

    stale = collect_pruning_candidates(repo_root, age_provider=lambda relative_path: ages.get(relative_path))

    assert [candidate.path.as_posix() for candidate in stale] == ["dev-docs/plans/old-plan.md"]


def test_collect_pruning_candidates_ignores_untracked_docs(tmp_path: Path) -> None:
    repo_root = tmp_path
    assessments = repo_root / "dev-docs" / "assessments"
    assessments.mkdir(parents=True)
    (assessments / "new.md").write_text("# new\n", encoding="utf-8")

    assert collect_pruning_candidates(repo_root, age_provider=lambda relative_path: None) == []
