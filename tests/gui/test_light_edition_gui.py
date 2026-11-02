"""GUI behavior of the Light edition: no PNG card, PNG helper refuses, missing meshes reported."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from nicegui import ui
from nicegui.testing import User

from guiskindose import _edition
from guiskindose.edition import EDITION_LIGHT, PngExportUnavailableError
from guiskindose.gui.state import state
from guiskindose.gui.ui_copy import copy_text

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


@pytest.fixture
def light(monkeypatch):
    monkeypatch.setattr(_edition, "EDITION", EDITION_LIGHT)


@pytest.fixture
def notes(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda message, **_k: calls.append(str(message)))
    return calls


async def _open_export_tab(user: User) -> None:
    await user.open("/")
    await user.should_see("8 · Export", retries=20)
    user.find("8 · Export").click()


@pytest.mark.asyncio
async def test_light_export_tab_hides_the_png_card(user: User, light) -> None:
    await _open_export_tab(user)
    await user.should_see("Interactive HTML dose map")
    await user.should_see(copy_text("export.light_edition.no_png"))
    await user.should_not_see("Download PNG")


@pytest.mark.asyncio
async def test_full_export_tab_offers_the_png_card(user: User) -> None:
    await _open_export_tab(user)
    await user.should_see("Download PNG")
    await user.should_not_see(copy_text("export.light_edition.no_png"))


def test_light_make_dosemap_png_raises_before_building_a_figure(light, monkeypatch) -> None:
    from guiskindose.gui import figures

    def refuse(**_kwargs):
        raise AssertionError("figure built in Light")

    monkeypatch.setattr(figures, "make_dosemap_fig", refuse)
    with pytest.raises(PngExportUnavailableError):
        figures.make_dosemap_png()


def test_settings_reports_a_saved_mesh_that_is_not_installed(light, monkeypatch) -> None:
    from guiskindose.gui.tabs import settings as settings_tab

    monkeypatch.setattr(state, "human_mesh", "senior_male")
    monkeypatch.setattr(
        settings_tab, "human_mesh_not_installed_message", lambda stem: "missing" if stem == "senior_male" else None
    )
    options = {"adult_male": "Adult Male", "hudfrid": "Hudfrid"}

    note = settings_tab._select_installed_mesh(options)

    assert state.human_mesh == "hudfrid"
    assert note == copy_text("settings.human_mesh.not_installed").format(label="Hudfrid")


def test_settings_stays_silent_for_an_installed_mesh(monkeypatch) -> None:
    from guiskindose.gui.tabs import settings as settings_tab

    monkeypatch.setattr(state, "human_mesh", "adult_male")
    assert settings_tab._select_installed_mesh({"adult_male": "Adult Male"}) is None
    assert state.human_mesh == "adult_male"


def test_settings_stays_silent_for_an_installed_alias(monkeypatch) -> None:
    """A legacy alias of an installed mesh is canonicalized without a notice."""
    from guiskindose.gui.tabs import settings as settings_tab

    monkeypatch.setattr(state, "human_mesh", "pediatric_5y_male")
    note = settings_tab._select_installed_mesh({"ped_5y_male": "Pediatric 5y Male", "hudfrid": "Hudfrid"})

    assert note is None
    assert state.human_mesh == "ped_5y_male"


def test_settings_explains_a_mesh_that_is_not_in_the_list(monkeypatch) -> None:
    """An unknown stem is replaced with Hudfrid even when another mesh is listed first."""
    from guiskindose.gui.tabs import settings as settings_tab

    monkeypatch.setattr(state, "human_mesh", "definitely_not_a_mesh")
    note = settings_tab._select_installed_mesh({"adult_male": "Adult Male", "hudfrid": "Hudfrid"})

    assert state.human_mesh == "hudfrid"
    assert note == copy_text("settings.human_mesh.unavailable").format(saved="definitely_not_a_mesh", label="Hudfrid")


def _starter_mesh_options() -> dict[str, str]:
    return {"adult_male": "Adult Male"}


def test_import_reports_a_mesh_that_is_not_installed(light, monkeypatch, notes) -> None:
    """Import uses the Settings replacement and surfaces its explanation."""
    from guiskindose.gui import helpers
    from guiskindose.gui.tabs import _run_config
    from guiskindose.gui.tabs import settings as settings_tab

    monkeypatch.setattr(state, "human_mesh", "senior_male")
    monkeypatch.setattr(helpers, "get_human_mesh_options", _starter_mesh_options)
    monkeypatch.setattr(
        settings_tab, "human_mesh_not_installed_message", lambda stem: "missing" if stem == "senior_male" else None
    )

    _run_config._notify_unavailable_imported_mesh()

    assert state.human_mesh == "adult_male"
    assert notes == [copy_text("settings.human_mesh.not_installed").format(label="Adult Male")]


def test_import_stays_silent_for_an_installed_mesh(monkeypatch, notes) -> None:
    """An installed imported mesh is not replaced and is not announced."""
    from guiskindose.gui import helpers
    from guiskindose.gui.tabs import _run_config

    monkeypatch.setattr(state, "human_mesh", "adult_male")
    monkeypatch.setattr(helpers, "get_human_mesh_options", _starter_mesh_options)

    _run_config._notify_unavailable_imported_mesh()

    assert state.human_mesh == "adult_male"
    assert notes == []


def test_calculate_refuses_a_mesh_that_is_not_installed(light, monkeypatch, notes) -> None:
    from guiskindose import phantom_mesh_names
    from guiskindose.gui.tabs import calculate as calc_tab

    monkeypatch.setattr(state, "phantom_model", "human")
    monkeypatch.setattr(state, "human_mesh", "senior_male")
    monkeypatch.setattr(
        phantom_mesh_names, "human_mesh_not_installed_message", lambda stem, **_k: f"{stem} is not installed"
    )

    assert calc_tab._CalculationController._human_mesh_is_installed() is False
    assert notes == ["senior_male is not installed"]

    monkeypatch.setattr(state, "phantom_model", "plane")
    assert calc_tab._CalculationController._human_mesh_is_installed() is True


@pytest.mark.asyncio
async def test_light_download_png_returns_early_with_the_light_notice(light, monkeypatch, notes) -> None:
    from guiskindose.gui.tabs import export as export_tab

    monkeypatch.setattr(state, "calculation_done", True)
    monkeypatch.setattr(export_tab, "_get_save_path", lambda *_a: pytest.fail("save dialog opened in Light"))
    monkeypatch.setattr(export_tab, "make_dosemap_png", lambda *_a: pytest.fail("PNG rendered in Light"))

    await export_tab.ExportTabController().download_png()

    assert notes == [copy_text("export.light_edition.no_png")]
