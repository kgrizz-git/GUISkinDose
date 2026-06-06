"""
Pytest configuration for NiceGUI smoke tests (Harness Phase 5).

Requires: pip install -e '.[gui]'  (includes pytest-asyncio)
"""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

pytest_plugins = ["nicegui.testing.user_plugin"]
