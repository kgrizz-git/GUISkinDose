"""Catalog-backed dialog content for classified export failures."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from nicegui import ui
from nicegui.testing import User

from guiskindose.export.failure_guidance import (
    PLOTLY_GET_CHROME_COMMAND,
    ExportFailure,
    ExportFailureKind,
)
from guiskindose.gui.components.export_failure_dialog import (
    copy_command,
    failure_dialog_content,
    show_export_failure_dialog,
)
from guiskindose.gui.ui_copy import copy_text

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


def test_missing_package_content_names_pip_package() -> None:
    failure = ExportFailure(
        kind=ExportFailureKind.MISSING_PACKAGE,
        format="docx",
        import_name="docx",
        pip_name="python-docx",
        command="pip install python-docx",
    )

    content = failure_dialog_content(failure)

    assert content.title == copy_text("export.failure.missing_package.title")
    assert content.body == copy_text("export.failure.missing_package.body")
    assert "DOCX" in content.detail[0]
    assert "python-docx" in content.detail[1]
    assert content.command == "pip install python-docx"
    assert content.command_label == copy_text("export.failure.install_package_label")
    assert content.retry == copy_text("export.failure.retry")


def test_missing_browser_content_has_chrome_command() -> None:
    content = failure_dialog_content(
        ExportFailure(kind=ExportFailureKind.MISSING_BROWSER, format="png", command=PLOTLY_GET_CHROME_COMMAND)
    )

    assert content.title == copy_text("export.failure.missing_browser.title")
    assert content.command == PLOTLY_GET_CHROME_COMMAND
    assert content.command_label == copy_text("export.failure.install_browser_label")


def test_portable_repair_content_has_no_command_or_pip() -> None:
    content = failure_dialog_content(ExportFailure(kind=ExportFailureKind.PORTABLE_REPAIR, format="png"))

    assert content.title == copy_text("export.failure.portable_repair.title")
    assert content.command is None
    assert content.command_label is None
    assert content.retry is None
    assert "pip" not in content.body.lower()


def test_incomplete_install_content_has_no_command() -> None:
    content = failure_dialog_content(ExportFailure(kind=ExportFailureKind.INCOMPLETE_INSTALL, format="xlsx"))

    assert content.title == copy_text("export.failure.incomplete_install.title")
    assert content.command is None
    assert content.retry == copy_text("export.failure.retry")


def test_unknown_failure_does_not_use_the_dialog() -> None:
    with pytest.raises(ValueError):
        failure_dialog_content(ExportFailure(kind=ExportFailureKind.UNKNOWN))


def test_copy_command_uses_clipboard(monkeypatch) -> None:
    copied: list[str] = []
    notices: list[tuple] = []
    monkeypatch.setattr(ui.clipboard, "write", lambda value: copied.append(value))
    monkeypatch.setattr(ui, "notify", lambda *a, **k: notices.append((a, k)))

    copy_command("pip install reportlab")

    assert copied == ["pip install reportlab"]
    assert notices


@pytest.mark.asyncio
async def test_dialog_renders_title_body_and_command(user: User) -> None:
    await user.open("/")
    from nicegui import Client

    client = next(iter(Client.instances.values()))
    failure = ExportFailure(
        kind=ExportFailureKind.MISSING_PACKAGE,
        format="pdf",
        import_name="reportlab",
        pip_name="reportlab",
        command="pip install reportlab",
    )
    with client:
        show_export_failure_dialog(failure)

    await user.should_see(copy_text("export.failure.missing_package.title"))
    await user.should_see(copy_text("export.failure.missing_package.body"))
    await user.should_see("pip install reportlab")
