"""Unit tests for scripts/check_todo_cleanup.py."""

from scripts.check_todo_cleanup import OpenItem, extract_paths, match_items, parse_open_items


def test_parse_open_items_collects_only_open_with_continuations():
    text = (
        "# Backlog\n\n"
        "- [ ] **DSfloat leak** — pydicom `DSfloat` values reach\n"
        "  `gui/tabs/data.py:126` and crash the socket emit.\n"
        "- [x] **Done thing** — already finished, touches `src/a.py`.\n"
        "- [ ] **Plain item** — no file references here.\n"
    )
    items = parse_open_items(text)
    assert [item.title for item in items] == ["**DSfloat leak** — pydicom `DSfloat` values reach", "**Plain item** — no file references here."]
    assert "gui/tabs/data.py:126" in items[0].text


def test_parse_open_items_stops_at_headings():
    text = "## Next Up\n\n- [ ] **A** — touches `src/a.py`.\n\n## Later\n\nSome prose.\n"
    items = parse_open_items(text)
    assert len(items) == 1


def test_extract_paths_backticked_and_bare():
    text = "See `gui/tabs/data.py:126`, `dataframe.to_dict`, src/guiskindose/gui/helpers.py and `CHANGELOG.md`."
    paths = extract_paths(text)
    assert "gui/tabs/data.py:126" in paths
    assert "src/guiskindose/gui/helpers.py" in paths
    assert "CHANGELOG.md" in paths
    assert "dataframe.to_dict" not in paths


def test_match_items_suffix_and_exact():
    items = [
        OpenItem(title="short form", text="touches gui/tabs/data.py"),
        OpenItem(title="exact", text="touches src/guiskindose/gui/helpers.py"),
        OpenItem(title="unrelated", text="touches docs/other.md"),
    ]
    changed = ["src/guiskindose/gui/tabs/data.py", "src/guiskindose/gui/helpers.py"]
    hits = match_items(items, changed)
    assert [item.title for item, _ in hits] == ["short form", "exact"]


def test_match_items_no_false_positive_on_prose():
    items = [OpenItem(title="plain", text="Just words, no file references.")]
    assert match_items(items, ["src/guiskindose/gui/helpers.py"]) == []
