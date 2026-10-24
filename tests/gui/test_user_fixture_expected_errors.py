"""An allowlisted ERROR must not fail NiceGUI's user fixture."""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


@pytest.fixture(autouse=True)
def _nonpropagating_helper_logger():
    logger = logging.getLogger("guiskindose.gui.helpers")
    previous = logger.propagate
    logger.propagate = False
    if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
        logger.addHandler(logging.NullHandler())
    yield
    logger.propagate = previous


async def test_allowlisted_error_does_not_fail_the_user_fixture(user) -> None:
    await user.open("/")
    logging.getLogger("guiskindose.gui.helpers").error("gui_test_expected_error")
