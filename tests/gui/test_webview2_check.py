"""WebView2 pre-check for the Windows native window, with an injected registry."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from guiskindose.gui import webview2
from guiskindose.gui.ui_copy import copy_text

_RUNTIME = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_BETA = "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}"
_NATIVE = r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
_WOW = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
_DOTNET = ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full", "Release")


class _FakeRegistry:
    """Registry reader backed by a dict; records every read."""

    def __init__(self, values: dict[tuple[str, str, str], object], dotnet: int | None) -> None:
        self.table = dict(values)
        if dotnet is not None:
            self.table[_DOTNET] = dotnet
        self.reads: list[tuple[str, str, str]] = []

    def __call__(self, hive: str, subkey: str, name: str) -> object:
        self.reads.append((hive, subkey, name))
        return self.table.get((hive, subkey, name))


def _reader(values: dict[tuple[str, str, str], object], *, dotnet: int | None = 528040) -> _FakeRegistry:
    return _FakeRegistry(values, dotnet)


def _pv(hive: str, view: str, client: str = _RUNTIME) -> tuple[str, str, str]:
    return (hive, rf"{view}\{client}", "pv")


@pytest.fixture(autouse=True)
def _amd64_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """pywebview's 64-bit HKLM view, independent of the machine running the tests."""
    monkeypatch.setattr(webview2, "_process_machine", lambda: "AMD64")


def _views_pywebview_reads(machine_name: str) -> set[tuple[str, str]]:
    """(hive, subkey) pairs ``edge_build`` opens for *machine_name*."""
    hklm = _NATIVE if machine_name == "x86" else _WOW
    return {
        (hive, rf"{view}\{client}")
        for client in webview2.WEBVIEW2_CLIENT_IDS
        for hive, view in (("HKEY_CURRENT_USER", _NATIVE), ("HKEY_LOCAL_MACHINE", hklm))
    }


@pytest.mark.parametrize(
    ("machine_name", "key", "ready"),
    [
        ("AMD64", _pv("HKEY_CURRENT_USER", _NATIVE), True),
        ("AMD64", _pv("HKEY_CURRENT_USER", _WOW), False),
        ("AMD64", _pv("HKEY_LOCAL_MACHINE", _WOW), True),
        ("x86", _pv("HKEY_CURRENT_USER", _NATIVE), True),
        ("x86", _pv("HKEY_CURRENT_USER", _WOW), False),
        ("x86", _pv("HKEY_LOCAL_MACHINE", _WOW), False),
        ("ARM64", _pv("HKEY_LOCAL_MACHINE", _WOW), True),
        ("ARM64", _pv("HKEY_LOCAL_MACHINE", _NATIVE), False),
        ("AMD64", _pv("HKEY_CURRENT_USER", _NATIVE, _BETA), True),
    ],
)
def test_readiness_follows_pywebview_registry_view(
    machine_name: str,
    key: tuple[str, str, str],
    ready: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(webview2, "_process_machine", lambda: machine_name)
    status = webview2.probe_webview2(_reader({key: "130.0.2849.80"}))
    assert status is not None
    assert status.runtime_ok is ready
    assert status.usable is ready


def test_native_path_only_follows_process_architecture(monkeypatch: pytest.MonkeyPatch) -> None:
    """A qualifying ``pv`` on the native HKLM key alone is ready only for an x86 process.

    pywebview 6.2.1 reads that key for HKLM when ``platform.machine()`` is ``x86``, and
    reads ``WOW6432Node`` for every other architecture. Approving the native key on a
    64-bit process lets startup continue into an MSHTML fallback.
    """
    reader_values = {_pv("HKEY_LOCAL_MACHINE", _NATIVE): "130.0.2849.80"}

    monkeypatch.setattr(webview2, "_process_machine", lambda: "AMD64")
    amd64 = webview2.probe_webview2(_reader(reader_values))
    assert amd64 is not None
    assert not amd64.runtime_ok
    assert not amd64.usable

    monkeypatch.setattr(webview2, "_process_machine", lambda: "ARM64")
    arm64 = webview2.probe_webview2(_reader(reader_values))
    assert arm64 is not None
    assert not arm64.usable

    monkeypatch.setattr(webview2, "_process_machine", lambda: "x86")
    x86 = webview2.probe_webview2(_reader(reader_values))
    assert x86 is not None
    assert x86.usable
    assert x86.summary()["runtime_version"] == "130.0.2849.80"


@pytest.mark.parametrize("machine_name", ["AMD64", "x86", "ARM64"])
def test_only_pywebview_views_are_read(machine_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webview2, "_process_machine", lambda: machine_name)
    reader = _reader({})
    webview2.probe_webview2(reader)
    pv_reads = {(hive, subkey) for hive, subkey, name in reader.reads if name == "pv"}
    assert pv_reads == _views_pywebview_reads(machine_name)


def test_newer_pv_on_the_ignored_view_does_not_count() -> None:
    reader = _reader(
        {
            _pv("HKEY_LOCAL_MACHINE", _NATIVE): "140.0.1.0",
            _pv("HKEY_LOCAL_MACHINE", _WOW): "120.0.2210.91",
        }
    )
    status = webview2.probe_webview2(reader)
    assert status is not None
    assert status.runtime_version == (120, 0, 2210, 91)


@pytest.mark.parametrize("pv", [None, "", "0.0.0.0", "not.a.version", "85.0.564.40"])
def test_absent_blank_uninstalled_or_too_old_runtime_is_unusable(pv) -> None:
    values = {} if pv is None else {_pv("HKEY_LOCAL_MACHINE", _WOW): pv}
    status = webview2.probe_webview2(_reader(values))
    assert status is not None
    assert not status.runtime_ok
    assert not status.usable


def test_newest_runtime_wins() -> None:
    reader = _reader({_pv("HKEY_CURRENT_USER", _NATIVE): "85.0.1.0", _pv("HKEY_LOCAL_MACHINE", _WOW): "120.0.2210.91"})
    status = webview2.probe_webview2(reader)
    assert status is not None
    assert status.runtime_version == (120, 0, 2210, 91)


@pytest.mark.parametrize("release", [None, 394801])
def test_old_or_missing_dotnet_is_unusable(release) -> None:
    status = webview2.probe_webview2(_reader({_pv("HKEY_CURRENT_USER", _NATIVE): "130.0.1.1"}, dotnet=release))
    assert status is not None
    assert status.runtime_ok
    assert not status.dotnet_ok
    assert not status.usable
    assert webview2.missing_runtime_message(status) == copy_text("native.webview2.dotnet_missing")


def test_missing_runtime_shows_the_evergreen_message_and_refuses() -> None:
    shown: list[str] = []

    ready = webview2.native_window_runtime_ready(_reader({}), show_message=shown.append)

    assert ready is False
    assert len(shown) == 1
    assert webview2.WEBVIEW2_DOWNLOAD_URL in shown[0]
    assert "Evergreen Bootstrapper" in shown[0]
    assert "not as administrator" in shown[0]


def test_usable_runtime_shows_nothing() -> None:
    shown: list[str] = []
    reader = _reader({_pv("HKEY_LOCAL_MACHINE", _WOW): "130.0.2849.80"})
    assert webview2.native_window_runtime_ready(reader, show_message=shown.append) is True
    assert shown == []


def test_off_windows_there_is_nothing_to_check(monkeypatch) -> None:
    monkeypatch.setattr(webview2, "winreg", None)
    assert webview2.default_registry_reader() is None
    assert webview2.probe_webview2() is None
    assert webview2.native_window_runtime_ready(show_message=lambda _m: pytest.fail("message shown")) is True


def test_winreg_reader_returns_none_for_absent_keys(monkeypatch) -> None:
    class FakeWinreg:
        HKEY_LOCAL_MACHINE = object()

        @staticmethod
        def OpenKey(_hive, _subkey):
            raise FileNotFoundError

    monkeypatch.setattr(webview2, "winreg", FakeWinreg)
    assert webview2._read_winreg("HKEY_LOCAL_MACHINE", r"SOFTWARE\Nope", "pv") is None


def test_run_gui_native_stops_before_ui_run_without_webview2(monkeypatch) -> None:
    import guiskindose.gui.app as gui_app

    monkeypatch.setattr(gui_app, "configure_logging", lambda **_k: None)
    monkeypatch.setattr(webview2, "native_window_runtime_ready", lambda: False)
    monkeypatch.setattr(gui_app.ui, "run", lambda **_k: pytest.fail("ui.run reached without WebView2"))
    monkeypatch.setattr(gui_app, "_configure_native_window", lambda: pytest.fail("window configured"))

    gui_app.run_gui(native=True)


def test_run_gui_browser_mode_skips_the_check(monkeypatch) -> None:
    import guiskindose.gui.app as gui_app

    monkeypatch.setattr(webview2, "native_window_runtime_ready", lambda: pytest.fail("checked in browser mode"))
    monkeypatch.setattr(gui_app, "configure_logging", lambda **_k: None)
    monkeypatch.setattr(gui_app, "_register_browser_shutdown_handler", lambda tasks: None)
    monkeypatch.setattr(gui_app, "register_gui_static_files", lambda: None)
    monkeypatch.setattr(gui_app, "generate_launch_token", lambda port: ("token", object()))
    monkeypatch.setattr(gui_app, "configure_loopback_security", lambda config: None)
    monkeypatch.setattr(gui_app.app, "add_middleware", lambda *a, **k: None)
    monkeypatch.setattr(gui_app, "_open_browser_when_ready", lambda url, port: None)
    ran: list[bool] = []
    monkeypatch.setattr(gui_app.ui, "run", lambda **_k: ran.append(True))

    gui_app.run_gui(native=False, port=8765)

    assert ran == [True]


def test_failure_is_logged_and_skips_print_without_a_console(monkeypatch, caplog, capsys) -> None:
    monkeypatch.setattr(webview2.sys, "stdout", None)

    with caplog.at_level("ERROR", logger=webview2.logger.name):
        assert webview2.native_window_runtime_ready(_reader({}), show_message=lambda _m: None) is False

    assert any(webview2.WEBVIEW2_DOWNLOAD_URL in record.getMessage() for record in caplog.records)
    monkeypatch.undo()
    assert capsys.readouterr().out == ""
