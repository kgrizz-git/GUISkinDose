"""Unit tests for scripts/check_doc_freshness.py link resolution."""

from pathlib import Path

from scripts.check_doc_freshness import (
    collect_markdown_files,
    find_broken_links,
    find_inventory_contradictions,
    is_external_link,
    resolve_relative_link,
    split_link_target,
)


def test_is_external_link():
    assert is_external_link("https://example.com/doc")
    assert is_external_link("http://example.com")
    assert is_external_link("mailto:team@example.com")
    assert not is_external_link("dev-docs/FEATURE_INVENTORY.md")


def test_split_link_target():
    assert split_link_target("#section") == ("", "section")
    assert split_link_target("foo.md#bar") == ("foo.md", "bar")
    assert split_link_target("plain.md") == ("plain.md", None)


def test_resolve_relative_link_from_repo_root(tmp_path: Path):
    repo_root = tmp_path
    source = repo_root / "AGENTS.md"
    source.write_text("# agents\n", encoding="utf-8")
    target = repo_root / "dev-docs" / "note.md"
    target.parent.mkdir(parents=True)
    target.write_text("# note\n", encoding="utf-8")

    resolved = resolve_relative_link(source, "dev-docs/note.md", repo_root)
    assert resolved == target.resolve()


def test_find_broken_links_reports_missing_target(tmp_path: Path):
    repo_root = tmp_path
    agents = repo_root / "AGENTS.md"
    agents.write_text("[missing](dev-docs/missing.md)\n", encoding="utf-8")

    broken = find_broken_links([agents], repo_root)
    assert len(broken) == 1
    assert broken[0].line_number == 1
    assert "missing.md" in broken[0].target


def test_find_broken_links_skips_external_and_same_page_anchor(tmp_path: Path):
    repo_root = tmp_path
    doc = repo_root / "README.md"
    doc.write_text(
        "[ext](https://example.com)\n"
        "[here](#section)\n"
        "[ok](./README.md)\n",
        encoding="utf-8",
    )

    broken = find_broken_links([doc], repo_root)
    assert broken == []


def test_find_broken_links_resolves_sibling_paths(tmp_path: Path):
    repo_root = tmp_path
    dev_docs = repo_root / "dev-docs"
    dev_docs.mkdir()
    source = dev_docs / "index.md"
    sibling = dev_docs / "other.md"
    sibling.write_text("# other\n", encoding="utf-8")
    source.write_text("[sibling](other.md)\n[bad](nope.md)\n", encoding="utf-8")

    broken = find_broken_links([source], repo_root)
    assert len(broken) == 1
    assert broken[0].target == "nope.md"


def test_collect_markdown_files_includes_optional_root_guidance(tmp_path: Path):
    repo_root = tmp_path
    (repo_root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (repo_root / "README.md").write_text("# readme\n", encoding="utf-8")
    dev_docs = repo_root / "dev-docs"
    dev_docs.mkdir()
    (dev_docs / "note.md").write_text("# note\n", encoding="utf-8")

    without_design = collect_markdown_files(repo_root)
    assert (repo_root / "AGENTS.md") in without_design
    assert (dev_docs / "note.md") in without_design
    assert (repo_root / "DESIGN.md") not in without_design

    (repo_root / "DESIGN.md").write_text("# design\n", encoding="utf-8")
    with_design = collect_markdown_files(repo_root)
    assert (repo_root / "DESIGN.md") in with_design

    (repo_root / "CLAUDE.md").write_text("# claude\n", encoding="utf-8")
    (repo_root / "GEMINI.md").write_text("# gemini\n", encoding="utf-8")
    (repo_root / "QWEN.md").write_text("# qwen\n", encoding="utf-8")
    with_agent_pointers = collect_markdown_files(repo_root)
    assert (repo_root / "CLAUDE.md") in with_agent_pointers
    assert (repo_root / "GEMINI.md") in with_agent_pointers
    assert (repo_root / "QWEN.md") in with_agent_pointers


def test_inventory_contradiction_detects_false_tabular_claim(tmp_path: Path):
    repo_root = tmp_path
    dev_docs = repo_root / "dev-docs"
    dev_docs.mkdir()
    (dev_docs / "FEATURE_INVENTORY.md").write_text(
        "| CSV/TSV/XLSX event-table input | Planned, not implemented | notes |\n",
        encoding="utf-8",
    )
    (repo_root / "AGENTS.md").write_text(
        "Tabular event-table input is now available for all exports.\n",
        encoding="utf-8",
    )

    contradictions = find_inventory_contradictions(repo_root)
    assert len(contradictions) == 1


def test_inventory_contradiction_ignores_planned_language(tmp_path: Path):
    repo_root = tmp_path
    dev_docs = repo_root / "dev-docs"
    dev_docs.mkdir()
    (dev_docs / "FEATURE_INVENTORY.md").write_text(
        "| CSV/TSV/XLSX event-table input | Planned, not implemented | notes |\n",
        encoding="utf-8",
    )
    (repo_root / "AGENTS.md").write_text(
        "Next input focus: support exported event tables via the staged plan.\n",
        encoding="utf-8",
    )

    assert find_inventory_contradictions(repo_root) == []


def test_inventory_contradiction_detects_false_tabular_claim_in_changelog(tmp_path: Path):
    repo_root = tmp_path
    dev_docs = repo_root / "dev-docs"
    dev_docs.mkdir()
    (dev_docs / "FEATURE_INVENTORY.md").write_text(
        "| CSV/TSV/XLSX event-table input | Planned, not implemented | notes |\n",
        encoding="utf-8",
    )
    (repo_root / "CHANGELOG.md").write_text(
        "- Tabular CSV input is now fully supported for all vendors.\n",
        encoding="utf-8",
    )

    contradictions = find_inventory_contradictions(repo_root)
    assert len(contradictions) == 1
    assert contradictions[0].source == Path("CHANGELOG.md")
