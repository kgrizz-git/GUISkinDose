"""
Pytest configuration for NiceGUI smoke tests (Harness Phase 5).

Requires: pip install -e '.[gui]'  (includes pytest-asyncio)

The NiceGUI test plugin (which provides the `user` fixture) is registered in the
top-level tests/conftest.py — pytest no longer allows `pytest_plugins` in a
nested conftest. This file just skips the GUI tests when NiceGUI is absent.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")
