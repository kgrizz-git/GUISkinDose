"""Tests for the pure helpers in ``packaging/portable/pngcheck.py`` (Full-shape PNG check)."""

from __future__ import annotations

import contextlib
import importlib
import sys
import time
from pathlib import Path

import pytest

from guiskindose.export import png_browser
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
    monkeypatch.setattr(png_browser, "_host_platform", lambda: "win32")
    (tmp_path / BROWSER_DIR).mkdir()
    (tmp_path / BROWSER_DIR / "chrome.exe").write_bytes(b"x")
    with pytest.raises(FileNotFoundError, match="browser_notices_missing"):
        pngcheck._check_bundle()


def test_check_bundle_fails_closed_without_browser(pngcheck, monkeypatch, tmp_path):
    monkeypatch.setattr(pngcheck, "app_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="bundled_browser_missing"):
        pngcheck._check_bundle()


def test_sampler_polls_until_stopped_and_survives_a_failed_probe(pngcheck, monkeypatch):
    import time

    calls: list[int] = []

    def probe():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("probe failed")
        return [{"pid": len(calls), "exe": "x"}]

    monkeypatch.setattr(pngcheck, "_windows_sampler", lambda: False)
    monkeypatch.setattr(pngcheck, "_list_processes", probe)
    monkeypatch.setattr(pngcheck, "_SAMPLE_INTERVAL_S", 0.01)
    sampler = pngcheck._ProcessSampler()
    sampler.start()
    time.sleep(0.1)
    sampler.stop()
    taken = len(sampler.samples)
    assert taken >= 2
    time.sleep(0.05)
    assert len(sampler.samples) == taken  # stopped
    assert len(pngcheck._merge_samples(sampler.samples)) == taken


def test_recording_wrapper_reraises_and_records_error(pngcheck):
    def real(*_a, **_k):
        raise KeyError("boom")

    errors: list = []
    wrapped = pngcheck._recording_figure_to_png(real, errors)
    with pytest.raises(KeyError):
        wrapped("fig")
    assert len(errors) == 1
    assert pngcheck._recording_figure_to_png(lambda *_a: b"png", errors)("fig") == b"png"


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

    # Unit tests drive ``_list_processes`` directly. The Windows watch is covered on its own.
    monkeypatch.setattr(pngcheck, "_windows_sampler", lambda: False)
    # A fake render finishes at once, so let the sampler take its first sample before the
    # payload runs (bounded, so a probe that always fails still proceeds).
    real_start = pngcheck._ProcessSampler.start

    def start_and_wait_for_first_probe(self):
        real_start(self)
        deadline = time.monotonic() + 0.5
        while not self.samples and time.monotonic() < deadline:
            time.sleep(0.005)

    monkeypatch.setattr(pngcheck._ProcessSampler, "start", start_and_wait_for_first_probe)
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
    with pytest.raises(pngcheck.RenderCheckError, match="browser_not_seen") as caught:
        pngcheck._render_pngs([])
    assert caught.value.counts["launched_outside"] == 0
    assert caught.value.counts["launched_inside"] == 0
    assert caught.value.counts["browser_processes"] == 0
    assert caught.value.counts["samples"] >= 1


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
    with pytest.raises(pngcheck.RenderCheckError, match="browser_outside") as caught:
        pngcheck._render_pngs([])
    assert caught.value.counts["launched_outside"] == 1
    assert caught.value.counts["launched_inside"] == 1


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
    assert "code" not in report["render"]
    assert "counts" not in report["render"]
    assert "page" not in report


def test_render_failure_records_which_condition_failed(pngcheck, monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(pngcheck, "_check_bundle", lambda: {"browser_present": True})

    def fail_render(_pages):
        raise pngcheck.RenderCheckError(
            "browser_not_seen",
            samples=4,
            rows=0,
            empty_exe_rows=0,
            browser_processes=0,
            launched_inside=0,
            launched_outside=0,
            system_chrome=0,
        )

    monkeypatch.setattr(pngcheck, "_render_pngs", fail_render)
    assert pngcheck.run_png_check(str(tmp_path), process_start=0.0) == 1
    report = json.loads((tmp_path / pngcheck.OWNED_SUBDIR / "pngcheck_report.json").read_text(encoding="utf-8"))
    assert report["render"]["code"] == "browser_not_seen"
    assert report["render"]["counts"] == {
        "samples": 4,
        "rows": 0,
        "empty_exe_rows": 0,
        "browser_processes": 0,
        "launched_inside": 0,
        "launched_outside": 0,
        "system_chrome": 0,
    }
    assert "page" not in report


def test_failure_record_drops_a_path_in_counts(pngcheck):
    class _Leaky(ValueError):
        def __init__(self) -> None:
            super().__init__("browser_not_seen")
            self.code = "browser_not_seen"
            self.counts = {"samples": 1, "exe": "C:/secret/chrome.exe"}

    report: dict = {}

    def fail():
        raise _Leaky()

    assert pngcheck._run_step(report, "render", fail) is False
    assert report["render"]["code"] == "browser_not_seen"
    assert "counts" not in report["render"]


class _FakeWatch:
    """A stand-in for the PowerShell watch: queued lines, then block until terminate."""

    def __init__(self, lines: list[str]) -> None:
        import threading

        self._pending = list(lines)
        self._released = threading.Event()
        self.stdout = self
        self.returncode: int | None = None

    def __iter__(self):
        return self

    def __next__(self) -> str:
        if self._pending:
            return self._pending.pop(0)
        self._released.wait(timeout=2)
        if self.returncode is not None or not self._pending:
            raise StopIteration
        return self._pending.pop(0)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 1
        self._released.set()

    def kill(self) -> None:
        self.terminate()

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode


def test_windows_watch_records_a_browser_line_and_stops(pngcheck, monkeypatch):
    import time

    payload = (
        '[{"ProcessId": 4, "ParentProcessId": 1, "ExecutablePath": "C:\\\\chromium\\\\chrome.exe",'
        ' "CommandLine": "chrome.exe --headless"}]'
    )
    watch = _FakeWatch(["not-json\n", payload + "\n"])
    monkeypatch.setattr(pngcheck, "_windows_sampler", lambda: True)
    monkeypatch.setattr(pngcheck, "_spawn_chrome_watch", lambda: watch)
    sampler = pngcheck._ProcessSampler()
    try:
        sampler.start()
        deadline = time.monotonic() + 1
        while not sampler.samples and time.monotonic() < deadline:
            time.sleep(0.01)
        assert [row["pid"] for row in sampler.samples[0]] == [4]
        assert sampler.samples[0][0]["exe"].endswith("chrome.exe")
    finally:
        sampler.stop()
    assert watch.returncode == 1


def test_sampler_stop_before_start_does_not_raise(pngcheck):
    pngcheck._ProcessSampler().stop()


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("", []),
        ("\r\n", []),
        ("null", []),
        ("[]", []),
        ('{"ProcessId": 1, "ParentProcessId": 0, "ExecutablePath": null, "CommandLine": null}', [1]),
        ('[{"ProcessId": 1, "ParentProcessId": 0, "ExecutablePath": "a", "CommandLine": "b"}, '
         '{"ProcessId": 2, "ParentProcessId": 1, "ExecutablePath": "a", "CommandLine": "c"}]\r\n', [1, 2]),
    ],
)
def test_list_processes_parses_every_powershell_shape(pngcheck, monkeypatch, stdout, expected):
    monkeypatch.setattr(pngcheck.sys, "platform", "win32")
    monkeypatch.setattr(pngcheck.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": stdout})())
    rows = pngcheck._list_processes()
    assert [row["pid"] for row in rows] == expected
    assert all(isinstance(row["exe"], str) for row in rows)


def test_render_pngs_fails_when_every_process_probe_failed(pngcheck, monkeypatch, tmp_path):
    from guiskindose.export import images

    monkeypatch.setattr(images, "figure_to_png", lambda *_a, **_k: b"\x89PNG\r\n\x1a\nxx")

    def fake_payload(_source, *, with_images):
        png = images.figure_to_png("fig")
        return type("P", (), {"images": [type("I", (), {"png_bytes": png})()]})()

    def probe():
        raise OSError("probe failed")

    _stub_render_environment(monkeypatch, pngcheck, tmp_path, fake_payload)
    monkeypatch.setattr(pngcheck, "_list_processes", probe)
    with pytest.raises(ValueError, match="process_sampling_failed"):
        pngcheck._render_pngs([])


def test_render_pngs_fails_when_any_image_failed(pngcheck, monkeypatch, tmp_path):
    from guiskindose.export import images
    from guiskindose.export.png_browser import PngRenderError

    results = iter([b"\x89PNG\r\n\x1a\nxx", None])

    def flaky_png(*_a, **_k):
        value = next(results)
        if value is None:
            raise PngRenderError()
        return value

    monkeypatch.setattr(images, "figure_to_png", flaky_png)

    def fake_payload(_source, *, with_images):
        pngs = []
        for _ in range(2):
            try:
                pngs.append(images.figure_to_png("fig"))
            except PngRenderError:
                pngs.append(None)
        return type("P", (), {"images": [type("I", (), {"png_bytes": png})() for png in pngs]})()

    _stub_render_environment(monkeypatch, pngcheck, tmp_path, fake_payload)
    with pytest.raises(PngRenderError):
        pngcheck._render_pngs([])
