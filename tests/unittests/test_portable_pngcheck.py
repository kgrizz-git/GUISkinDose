"""Tests for the pure helpers in ``packaging/portable/pngcheck.py`` (Full-shape PNG check)."""

from __future__ import annotations

import contextlib
import importlib
import sys
from pathlib import Path

import pytest

from guiskindose.export.png_browser import BROWSER_DIR

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


def test_failed_render_skips_page_step(pngcheck, monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(pngcheck, "_check_bundle", lambda: {"browser_present": True})

    def fail_render(_pages):
        raise RuntimeError("render failed")

    monkeypatch.setattr(pngcheck, "_render_pngs", fail_render)
    assert pngcheck.run_png_check(str(tmp_path), process_start=0.0) == 1
    report = json.loads((tmp_path / pngcheck.OWNED_SUBDIR / "pngcheck_report.json").read_text(encoding="utf-8"))
    assert report["render"]["error_type"] == "RuntimeError"
    assert "page" not in report
    assert report["passed"] is False


def test_bundled_browser_honors_patched_app_dir(pngcheck, monkeypatch, tmp_path):
    monkeypatch.setattr(pngcheck, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "win32")
    (tmp_path / BROWSER_DIR).mkdir()
    (tmp_path / BROWSER_DIR / "chrome.exe").write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match="browser_notices_missing"):
        pngcheck._check_bundle()


def test_check_bundle_fails_closed_without_browser(pngcheck, monkeypatch, tmp_path):
    monkeypatch.setattr(pngcheck, "app_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="bundled_browser_missing"):
        pngcheck._check_bundle()


def test_sampler_records_processes_while_render_runs(pngcheck, monkeypatch):
    import threading

    release = threading.Event()
    seen: list[int] = []
    monkeypatch.setattr(pngcheck, "_list_processes", lambda: seen.append(1) or [{"pid": len(seen), "exe": "x"}])
    monkeypatch.setattr(pngcheck, "_SAMPLE_INTERVAL_S", 0.01)

    def real(*_a, **_k):
        release.wait(0.2)
        return b"png"

    samples: list = []
    errors: list = []
    wrapped = pngcheck._sampling_figure_to_png(real, samples, errors)
    assert wrapped("fig") == b"png"
    assert len(samples) >= 2
    assert errors == []
    merged = pngcheck._merge_samples(samples)
    assert len(merged) == len(samples)


def test_sampler_reraises_and_records_error(pngcheck, monkeypatch):
    monkeypatch.setattr(pngcheck, "_list_processes", lambda: [])

    def real(*_a, **_k):
        raise KeyError("boom")

    samples: list = []
    errors: list = []
    wrapped = pngcheck._sampling_figure_to_png(real, samples, errors)
    with pytest.raises(KeyError):
        wrapped("fig")
    assert len(errors) == 1


def _stub_render_environment(monkeypatch, pngcheck, tmp_path, images):
    """Fake the heavy pieces of ``_render_pngs`` so no browser or calculation runs."""
    import types

    from kaleido import _page_generator

    monkeypatch.setattr(pngcheck, "app_dir", lambda: tmp_path.resolve())
    monkeypatch.setattr(pngcheck, "_pkg", lambda *_a: "rdsr.dcm")
    monkeypatch.setattr(pngcheck, "_list_processes", lambda: [])
    fake_main = types.ModuleType("guiskindose.main")
    fake_main.build_cli_export_source = lambda *_a: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "guiskindose.main", fake_main)
    import guiskindose.export as export_pkg

    monkeypatch.setattr(export_pkg, "collect_export_payload", images)
    return _page_generator


def test_render_pngs_uses_figure_to_png_and_restores_it(pngcheck, monkeypatch, tmp_path):
    import kaleido

    from guiskindose.export import images
    from guiskindose.export.png_browser import BundledBrowserUnavailableError

    start_calls: list = []
    monkeypatch.setattr(kaleido, "start_sync_server", lambda *a, **k: start_calls.append(a), raising=False)
    seen_wrapped: list = []

    def failing_png(*_a, **_k):
        raise BundledBrowserUnavailableError()

    monkeypatch.setattr(images, "figure_to_png", failing_png)

    def fake_payload(_source, *, with_images):
        seen_wrapped.append(images.figure_to_png is not failing_png)
        with contextlib.suppress(BundledBrowserUnavailableError):  # the payload swallows it too
            images.figure_to_png("fig")
        return type("P", (), {"images": []})()

    page_gen = _stub_render_environment(monkeypatch, pngcheck, tmp_path, fake_payload)
    original_index = page_gen.PageGenerator.generate_index
    with pytest.raises(BundledBrowserUnavailableError):
        pngcheck._render_pngs([])
    assert seen_wrapped == [True]  # the payload saw the sampling wrapper
    assert images.figure_to_png is failing_png  # restored
    assert page_gen.PageGenerator.generate_index is original_index
    assert start_calls == []


def test_render_pngs_restores_figure_to_png_on_error(pngcheck, monkeypatch, tmp_path):
    from guiskindose.export import images

    marker = lambda *_a, **_k: b"png"  # noqa: E731
    monkeypatch.setattr(images, "figure_to_png", marker)

    def boom(_source, *, with_images):
        raise RuntimeError("payload failed")

    _stub_render_environment(monkeypatch, pngcheck, tmp_path, boom)
    with pytest.raises(RuntimeError, match="payload failed"):
        pngcheck._render_pngs([])
    assert images.figure_to_png is marker


def test_render_pngs_describes_processes_sampled_during_render(pngcheck, monkeypatch, tmp_path):
    import os

    from guiskindose.export import images

    inside = tmp_path.resolve() / "chromium" / "chrome.exe"
    live = [{"pid": 10, "ppid": os.getpid(), "exe": str(inside), "cmd": f"{inside} --headless"}]
    state = {"running": False}

    def real_png(*_a, **_k):
        state["running"] = True
        import time

        time.sleep(0.1)  # let the sampler observe the live browser
        state["running"] = False
        return b"\x89PNG\r\n\x1a\nxx"

    monkeypatch.setattr(images, "figure_to_png", real_png)

    def fake_payload(_source, *, with_images):
        png = images.figure_to_png("fig")  # the browser has exited by the time this returns
        return type("P", (), {"images": [type("I", (), {"png_bytes": png})()]})()

    _stub_render_environment(monkeypatch, pngcheck, tmp_path, fake_payload)
    monkeypatch.setattr(pngcheck, "_list_processes", lambda: live if state["running"] else [])
    monkeypatch.setattr(pngcheck, "_SAMPLE_INTERVAL_S", 0.01)
    result = pngcheck._render_pngs([])
    assert result["launched_from_onedir"] == ["chromium/chrome.exe"]
    assert result["launched_outside_onedir"] == 0
    assert result["png_images"] == 1


def test_render_pngs_fails_when_no_sample_saw_a_browser(pngcheck, monkeypatch, tmp_path):
    from guiskindose.export import images

    monkeypatch.setattr(images, "figure_to_png", lambda *_a, **_k: b"\x89PNG\r\n\x1a\nxx")

    def fake_payload(_source, *, with_images):
        png = images.figure_to_png("fig")
        return type("P", (), {"images": [type("I", (), {"png_bytes": png})()]})()

    _stub_render_environment(monkeypatch, pngcheck, tmp_path, fake_payload)
    with pytest.raises(ValueError, match="browser_not_bundled_copy"):
        pngcheck._render_pngs([])


def test_render_pngs_fails_when_a_browser_ran_outside_the_onedir(pngcheck, monkeypatch, tmp_path):
    import os

    from guiskindose.export import images

    outside = tmp_path.parent / "chrome.exe"
    inside = tmp_path.resolve() / "chromium" / "chrome.exe"
    rows = [
        {"pid": 10, "ppid": os.getpid(), "exe": str(inside), "cmd": "c --headless"},
        {"pid": 11, "ppid": os.getpid(), "exe": str(outside), "cmd": "c --headless"},
    ]
    monkeypatch.setattr(images, "figure_to_png", lambda *_a, **_k: b"\x89PNG\r\n\x1a\nxx")

    def fake_payload(_source, *, with_images):
        png = images.figure_to_png("fig")
        return type("P", (), {"images": [type("I", (), {"png_bytes": png})()]})()

    _stub_render_environment(monkeypatch, pngcheck, tmp_path, fake_payload)
    monkeypatch.setattr(pngcheck, "_list_processes", lambda: rows)
    monkeypatch.setattr(pngcheck, "_SAMPLE_INTERVAL_S", 0.01)
    with pytest.raises(ValueError, match="browser_not_bundled_copy"):
        pngcheck._render_pngs([])


def test_run_png_check_records_bundled_browser_error_type(pngcheck, monkeypatch, tmp_path):
    import json

    from guiskindose.export.png_browser import BundledBrowserUnavailableError

    monkeypatch.setattr(pngcheck, "_check_bundle", lambda: {"browser_present": True})

    def fail_render(_pages):
        raise BundledBrowserUnavailableError()

    monkeypatch.setattr(pngcheck, "_render_pngs", fail_render)
    assert pngcheck.run_png_check(str(tmp_path), process_start=0.0) == 1
    report = json.loads((tmp_path / pngcheck.OWNED_SUBDIR / "pngcheck_report.json").read_text(encoding="utf-8"))
    assert report["render"]["error_type"] == "BundledBrowserUnavailableError"
    assert "page" not in report
