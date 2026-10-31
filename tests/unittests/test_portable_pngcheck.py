"""Tests for the pure helpers in ``packaging/portable/pngcheck.py`` (Full-shape PNG check)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_PORTABLE = Path(__file__).resolve().parents[2] / "packaging" / "portable"


@pytest.fixture(scope="module")
def pngcheck():
    sys.path.insert(0, str(_PORTABLE))
    try:
        yield importlib.import_module("pngcheck")
    finally:
        sys.path.remove(str(_PORTABLE))


def test_page_check_rejects_http_script(pngcheck):
    with pytest.raises(ValueError, match="http_script"):
        pngcheck._check_page(['<script src="https://cdn.plot.ly/plotly.js"></script>'])


def test_page_check_accepts_file_scripts(pngcheck):
    found = pngcheck._check_page(['<script src="file:///x/plotly.min.js" charset="utf-8"></script>'])
    assert found == {"pages_captured": 1, "http_script_refs": 0, "mathjax_referenced": False}


def test_page_check_requires_a_page(pngcheck):
    with pytest.raises(ValueError, match="not_captured"):
        pngcheck._check_page([])


def test_descendants_walks_the_tree(pngcheck):
    rows = [
        {"pid": 2, "ppid": 1, "exe": "a", "cmd": ""},
        {"pid": 3, "ppid": 2, "exe": "b", "cmd": ""},
        {"pid": 4, "ppid": 9, "exe": "c", "cmd": ""},
    ]
    assert sorted(row["pid"] for row in pngcheck._descendants(rows, 1)) == [2, 3]


def test_describe_launch_splits_inside_and_outside(pngcheck, monkeypatch, tmp_path):
    import os

    monkeypatch.setattr(pngcheck, "app_dir", lambda: tmp_path.resolve())
    inside = tmp_path / "chromium" / "chrome.exe"
    rows = [
        {"pid": 10, "ppid": os.getpid(), "exe": str(inside), "cmd": f"{inside} --headless --no-sandbox --foo"},
        {"pid": 11, "ppid": 10, "exe": str(tmp_path.parent / "chrome.exe"), "cmd": "chrome.exe --type=renderer"},
    ]
    found = pngcheck._describe_launch(rows)
    assert found["launched_from_onedir"] == ["chromium/chrome.exe"]
    assert found["launched_outside_onedir"] == 1
    assert found["flags"] == ["--headless", "--no-sandbox"]


def test_inside_is_containment_not_prefix(pngcheck, tmp_path):
    base = tmp_path / "GUISkinDose"
    (base / "chromium").mkdir(parents=True)
    assert pngcheck._inside(str(base / "chromium" / "chrome.exe"), base)
    assert not pngcheck._inside(str(tmp_path / "GUISkinDose-other" / "chrome.exe"), base)
    assert not pngcheck._inside("", base)


def test_credits_placeholder_fails(monkeypatch):
    monkeypatch.syspath_prepend(str(_PORTABLE))
    credits = importlib.import_module("dump_chromium_credits")
    assert credits.credits_exit_code(5_000_000, 497, placeholder=False) == 0
    assert credits.credits_exit_code(5_000_000, 497, placeholder=True) == 1
    assert credits.credits_exit_code(462, 0, placeholder=False) == 1
