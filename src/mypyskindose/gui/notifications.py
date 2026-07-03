"""Global defaults for GUI toast notifications.

Every tab calls ``ui.notify(...)`` directly. Rather than thread position/timeout
kwargs through ~40 call sites (and every future one), we patch ``ui.notify`` once
at app startup to inject our defaults: toasts appear at the **top** of the screen
and stay **longer** than Quasar's 5 s default. Explicit ``position``/``timeout``
kwargs at a call site still win, so persistent toasts (``timeout=0``) are
unaffected.

``ui`` is a single shared module object, so replacing its ``notify`` attribute is
seen by every ``from nicegui import ui`` importer.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

# Toast position on screen and how long it lingers (milliseconds; Quasar's
# default is 5000). Bumped so users have time to read export/calculation
# messages before they disappear.
_DEFAULT_POSITION = "top"
_DEFAULT_TIMEOUT_MS = 8000


def install_notification_defaults() -> None:
    """Patch ``ui.notify`` so toasts default to top-of-screen and a longer timeout.

    Idempotent: safe to call more than once (only the first call wraps).
    """
    original = ui.notify
    if getattr(original, "_mpsd_patched", False):
        return

    def notify(message: Any = "", **kwargs: Any) -> Any:
        kwargs.setdefault("position", _DEFAULT_POSITION)
        kwargs.setdefault("timeout", _DEFAULT_TIMEOUT_MS)
        return original(message, **kwargs)

    notify._mpsd_patched = True  # type: ignore[attr-defined]
    ui.notify = notify  # type: ignore[assignment]
