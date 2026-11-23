"""Corrections-tab text inputs: a cleared field means unset (``None``).

NiceGUI 4 stores ``''`` in a text input the user clears. The two optional
kerma-meter state attributes are ``str | None`` and use ``None`` for unset, so
the binding must map between the two. These tests drive the real page.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from nicegui import ui
from nicegui.testing import User

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_FIELDS = (
    ("Correction table path (CSV/TSV/XLSX/JSON)", "kerma_meter_file"),
    ("Explicit equipment label (optional override)", "kerma_meter_explicit_label"),
)


async def _corrections_inputs(user: User) -> dict[str, ui.input]:
    """Open the app, show the Corrections tab, and map its text inputs by label."""
    await user.open("/")
    user.find("4 · Corrections").click()
    inputs: dict[str, ui.input] = {}
    for element in user.find(ui.input).elements:
        label = element.props.get("label")
        if isinstance(label, str):
            inputs[label] = element
    return inputs


@pytest.mark.asyncio
@pytest.mark.parametrize("label,attribute", _FIELDS)
async def test_clearing_a_field_unsets_state(user: User, label: str, attribute: str) -> None:
    """Typing sets the state string; clearing the input stores None, never ''."""
    from guiskindose.gui.state import state

    field = (await _corrections_inputs(user))[label]

    with user:
        field.value = "/data/cf/corrections.csv"
    assert getattr(state, attribute) == "/data/cf/corrections.csv"

    with user:
        field.value = ""
    assert getattr(state, attribute) is None
