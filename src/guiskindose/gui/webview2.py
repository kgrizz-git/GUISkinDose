"""WebView2 pre-check for the native window on Windows (PORTABLE_APP_PLAN.md Phase 1).

pywebview 6 falls back to the old MSHTML engine when it finds no WebView2 runtime.
NiceGUI does not run there, and the window can fail while the server stays up. So
before ``ui.run(native=True)`` the app reads the same registry values that pywebview's
``_is_chromium()`` reads, and stops with a message when no runtime is usable.

``_is_chromium()`` is not called. It returns true as soon as a runtime path setting is
non-empty, and it cannot be pointed at a test registry. This check reads both hives,
HKCU and HKLM, and both the native and ``WOW6432Node`` views of each, where pywebview
reads one view per hive. It also requires .NET Framework 4.6.2 or later, which
pywebview's WinForms backend needs.

No installer is launched and MSHTML is never used. Off Windows, ``winreg`` does not
import and the check passes, because the native window there is not WebView2. Tests
inject a fake registry reader.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

try:
    import winreg
except ImportError:  # not Windows: there is no WebView2 to check
    winreg = None

logger = logging.getLogger(__name__)

# (hive name, subkey, value name) -> the value, or None when the key or value is absent.
RegistryReader = Callable[[str, str, str], object]

# Microsoft's WebView2 page, which offers the Evergreen Bootstrapper. Run without
# elevation, the bootstrapper installs for the current user only.
WEBVIEW2_DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"

# pywebview's thresholds (webview/platforms/winforms.py, 6.2.1).
MIN_WEBVIEW2_VERSION = (86, 0, 622, 0)
DOTNET_462_RELEASE = 394802
_DOTNET_KEY = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"

# EdgeUpdate client ids pywebview accepts: runtime, beta, dev, canary.
WEBVIEW2_CLIENT_IDS = (
    "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
    "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",
    "{65C35B14-6C1D-4122-AC46-7148CC9D6497}",
)
_HIVES = ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE")
_VIEWS = (r"SOFTWARE\Microsoft\EdgeUpdate\Clients", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients")


@dataclass(frozen=True)
class WebView2Status:
    """What the registry says about the runtime the native window needs."""

    runtime_version: tuple[int, ...] | None
    dotnet_release: int | None

    @property
    def runtime_ok(self) -> bool:
        """True when a WebView2 runtime at or above pywebview's minimum is registered."""
        return self.runtime_version is not None and self.runtime_version >= MIN_WEBVIEW2_VERSION

    @property
    def dotnet_ok(self) -> bool:
        """True when .NET Framework 4.6.2 or later is installed."""
        return self.dotnet_release is not None and self.dotnet_release >= DOTNET_462_RELEASE

    @property
    def usable(self) -> bool:
        """True when the native window can use WebView2."""
        return self.runtime_ok and self.dotnet_ok

    def summary(self) -> dict[str, object]:
        """Booleans and the runtime version only; safe for a log or a CI report."""
        version = ".".join(str(part) for part in self.runtime_version) if self.runtime_version else None
        return {
            "runtime_version": version,
            "runtime_ok": self.runtime_ok,
            "dotnet_ok": self.dotnet_ok,
            "usable": self.usable,
        }


def _read_winreg(hive: str, subkey: str, value_name: str) -> object:
    """Read one registry value with ``winreg``; ``None`` when it is absent."""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(getattr(winreg, hive), subkey) as key:
            return winreg.QueryValueEx(key, value_name)[0]
    except OSError:
        return None


def default_registry_reader() -> RegistryReader | None:
    """The ``winreg`` reader on Windows, else ``None``."""
    return _read_winreg if winreg is not None else None


def _parse_version(raw: object) -> tuple[int, ...] | None:
    """``"120.0.2210.91"`` -> ``(120, 0, 2210, 91)``; ``None`` for blanks, junk, or all zeros.

    An uninstalled runtime can leave ``pv`` as ``0.0.0.0``, so all zeros means absent.
    """
    if not isinstance(raw, str):
        return None
    try:
        parts = tuple(int(part) for part in raw.strip().split("."))
    except ValueError:
        return None
    return parts if any(parts) else None


def _newest_runtime(reader: RegistryReader) -> tuple[int, ...] | None:
    """Highest registered runtime version across every client id, hive, and view."""
    found = [
        version
        for client in WEBVIEW2_CLIENT_IDS
        for hive in _HIVES
        for view in _VIEWS
        if (version := _parse_version(reader(hive, rf"{view}\{client}", "pv"))) is not None
    ]
    return max(found, default=None)


def probe_webview2(reader: RegistryReader | None = None) -> WebView2Status | None:
    """Read the runtime and .NET versions; ``None`` off Windows (no registry)."""
    reader = reader or default_registry_reader()
    if reader is None:
        return None
    release = reader("HKEY_LOCAL_MACHINE", _DOTNET_KEY, "Release")
    return WebView2Status(
        runtime_version=_newest_runtime(reader),
        dotnet_release=release if isinstance(release, int) else None,
    )


def missing_runtime_message(status: WebView2Status) -> str:
    """User-facing explanation for an unusable *status*."""
    from .ui_copy import copy_text

    if not status.dotnet_ok:
        return copy_text("native.webview2.dotnet_missing")
    return copy_text("native.webview2.runtime_missing").format(url=WEBVIEW2_DOWNLOAD_URL)


def _show_message_box(text: str) -> None:
    """Show *text* in a Windows message box; a windowed build has no console."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "GUISkinDose", 0x10)  # MB_ICONERROR
    except (AttributeError, OSError):
        logger.warning("WebView2 message box could not be shown")


def native_window_runtime_ready(
    reader: RegistryReader | None = None,
    show_message: Callable[[str], None] | None = None,
) -> bool:
    """True when the native window can open. Otherwise show why and return False.

    Off Windows there is no registry and the answer is True.
    """
    status = probe_webview2(reader)
    if status is None:
        return True
    if status.usable:
        logger.info("WebView2 pre-check passed (runtime %s)", status.summary()["runtime_version"])
        return True
    logger.error("WebView2 pre-check failed: runtime_ok=%s dotnet_ok=%s", status.runtime_ok, status.dotnet_ok)
    message = missing_runtime_message(status)
    print(message)
    (show_message or _show_message_box)(message)
    return False
