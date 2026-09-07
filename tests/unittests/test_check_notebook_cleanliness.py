"""Tests for the canonical notebook cleanliness guard."""

import json
from pathlib import Path

from scripts.check_notebook_cleanliness import notebook_cleanliness_issues


def write_notebook(path: Path, cells: list[object]) -> None:
    path.write_text(json.dumps({"cells": cells}), encoding="utf-8")


def test_notebook_cleanliness_accepts_unexecuted_code_cells(tmp_path: Path):
    path = tmp_path / "clean.ipynb"
    write_notebook(
        path,
        [{"cell_type": "markdown", "source": ["# Tutorial"]}, {"cell_type": "code", "execution_count": None, "outputs": []}],
    )

    assert notebook_cleanliness_issues(path) == []


def test_notebook_cleanliness_reports_execution_counts_and_outputs(tmp_path: Path):
    path = tmp_path / "executed.ipynb"
    write_notebook(path, [{"cell_type": "code", "execution_count": 1, "outputs": [{"output_type": "stream"}]}])

    assert notebook_cleanliness_issues(path) == [
        "code cell 0 has an execution count",
        "code cell 0 has 1 stored output(s)",
    ]


def test_notebook_cleanliness_reports_invalid_notebook_json(tmp_path: Path):
    path = tmp_path / "invalid.ipynb"
    path.write_text("not JSON", encoding="utf-8")

    assert len(notebook_cleanliness_issues(path)) == 1
    assert "could not read valid notebook JSON" in notebook_cleanliness_issues(path)[0]


def test_notebook_cleanliness_reports_non_object_json_and_malformed_cells(tmp_path: Path):
    non_object_path = tmp_path / "non_object.ipynb"
    non_object_path.write_text("[]", encoding="utf-8")
    malformed_cell_path = tmp_path / "malformed_cell.ipynb"
    write_notebook(malformed_cell_path, ["not a cell object"])

    assert notebook_cleanliness_issues(non_object_path) == ["invalid notebook JSON structure (not an object)"]
    assert notebook_cleanliness_issues(malformed_cell_path) == ["cell 0 is not an object"]
