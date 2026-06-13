"""Top-level pytest configuration.

`pytest_plugins` must be declared in a top-level conftest — pytest no longer
allows it in nested conftests (it would silently affect the whole suite). The
NiceGUI test plugin provides the `user` fixture the GUI tests rely on, so it is
registered here, but only when NiceGUI (the `[gui]` extra) is installed. That
keeps the rest of the suite collectable without the GUI dependencies.
"""

from __future__ import annotations

pytest_plugins: list[str] = []

try:
    import nicegui  # noqa: F401
except ImportError:
    pass
else:
    pytest_plugins.append("nicegui.testing.user_plugin")
