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


@pytest.mark.parametrize(
    "key",
    [
        _pv("HKEY_CURRENT_USER", _NATIVE),
        _pv("HKEY_CURRENT_USER", _WOW),
        _pv("HKEY_LOCAL_MACHINE", _NATIVE),
        _pv("HKEY_LOCAL_MACHINE", _WOW),
        _pv("HKEY_CURRENT_USER", _NATIVE, _BETA),
    ],
)
def test_runtime_found_in_any_hive_and_view(key) -> None:
    status = webview2.probe_webview2(_reader({key: "130.0.2849.80"}))
    assert status is not None
    assert status.usable
    assert status.summary() == {"runtime_version": "130.0.2849.80", "runtime_ok": True, "dotnet_ok": True, "usable": True}


def test_every_client_hive_and_view_is_read() -> None:
    reader = _reader({})
    webview2.probe_webview2(reader)
    pv_reads = {(hive, subkey) for hive, subkey, name in reader.reads if name == "pv"}
    assert len(pv_reads) == len(webview2.WEBVIEW2_CLIENT_IDS) * 2 * 2


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
