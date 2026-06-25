"""Unit tests for scripts/check_agent_guidance.py."""

from pathlib import Path

from scripts.check_agent_guidance import collect_agent_guidance_warnings


def test_collect_agent_guidance_warnings_accepts_pointer_files(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    (repo_root / "dev-docs").mkdir()
    (repo_root / "dev-docs" / "AGENT_PLAYBOOK.md").write_text("# Playbook\n", encoding="utf-8")
    (repo_root / "CLAUDE.md").write_text("@AGENTS.md\n\nSee dev-docs/AGENT_PLAYBOOK.md.\n", encoding="utf-8")
    (repo_root / "GEMINI.md").write_text("# Gemini\n\nRead AGENTS.md first.\n", encoding="utf-8")
    (repo_root / "QWEN.md").write_text("# Qwen\n\nRead AGENTS.md first.\n", encoding="utf-8")
    (repo_root / "dev-docs" / "TO_DO.md").write_text("# TO DO\n\n- [x] recent\n", encoding="utf-8")

    assert collect_agent_guidance_warnings(repo_root) == []


def test_collect_agent_guidance_warnings_flags_unlinked_tool_file(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "CLAUDE.md").write_text("# Claude-only duplicate instructions\n", encoding="utf-8")

    warnings = collect_agent_guidance_warnings(repo_root)

    assert any(warning.path == Path("CLAUDE.md") and "does not mention AGENTS.md" in warning.message for warning in warnings)


def test_collect_agent_guidance_warnings_flags_overgrown_todo_completed_section(tmp_path: Path) -> None:
    repo_root = tmp_path
    dev_docs = repo_root / "dev-docs"
    dev_docs.mkdir()
    completed = "\n".join(f"- [x] finished {index}" for index in range(11))
    (dev_docs / "TO_DO.md").write_text(f"# TO DO\n\n## Completed\n\n{completed}\n", encoding="utf-8")

    warnings = collect_agent_guidance_warnings(repo_root)

    assert any(warning.path == Path("dev-docs/TO_DO.md") and "completed checklist items" in warning.message for warning in warnings)


def test_collect_agent_guidance_warnings_flags_completed_active_execution_plan(tmp_path: Path) -> None:
    repo_root = tmp_path
    plans = repo_root / "dev-docs" / "plans"
    plans.mkdir(parents=True)
    (plans / "small-plan.md").write_text("- [x] one\n- [x] two\n", encoding="utf-8")
    (plans / "GUI_PLAN.md").write_text("- [x] master plans are exempt\n", encoding="utf-8")

    warnings = collect_agent_guidance_warnings(repo_root)

    assert any(warning.path == Path("dev-docs/plans/small-plan.md") and "appears complete" in warning.message for warning in warnings)
    assert not any(warning.path == Path("dev-docs/plans/GUI_PLAN.md") for warning in warnings)


def test_collect_agent_guidance_warnings_flags_undocumented_model_family_file(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "KIMI.md").write_text("# Kimi\n\nRead AGENTS.md.\n", encoding="utf-8")

    warnings = collect_agent_guidance_warnings(repo_root)

    assert any(warning.path == Path("KIMI.md") and "undocumented agent guidance filename" in warning.message for warning in warnings)
