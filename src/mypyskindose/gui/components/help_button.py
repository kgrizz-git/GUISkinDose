"""Reusable help button component for displaying markdown help content."""

from pathlib import Path
from typing import Optional

from nicegui import ui

from ..ui_copy import copy_text


class HelpButton:
    """A help button that displays markdown content in a dialog.

    This component provides a consistent way to add contextual help throughout
    the GUI. It creates a small "?" button that opens a scrollable dialog
    with markdown-formatted help text.

    Args:
        title: Title displayed in the dialog header.
        content: Markdown content to display. Either this or content_path must be provided.
        content_path: Path to a markdown file to load. Relative paths are resolved
            from the gui/help/ directory.
        icon: Icon to use for the button (default: "help").
        button_text: Text for the button (default: "", icon-only).
        help_id: Optional registry id used by documentation harness checks.
    """

    def __init__(
        self,
        title: str,
        content: Optional[str] = None,
        content_path: Optional[str] = None,
        icon: str = "help",
        button_text: str = "",
        help_id: Optional[str] = None,
    ):
        if content is None and content_path is None:
            raise ValueError("Either content or content_path must be provided")

        self.title = title
        self.icon = icon
        self.button_text = button_text
        self.help_id = help_id

        # Load content
        if content is not None:
            self.content = content
        elif content_path is not None:
            self.content = self._load_content(content_path)
        else:
            raise ValueError("Either content or content_path must be provided")

        # Create the button
        self._create_button()

    def _load_content(self, content_path: str) -> str:
        """Load markdown content from a file.

        Args:
            content_path: Relative path to the markdown file (from gui/help/).

        Returns:
            The file contents as a string.

        Raises:
            FileNotFoundError: If the help file doesn't exist.
        """
        # Resolve path relative to gui/help/ directory
        help_dir = Path(__file__).parent.parent / "help"
        full_path = help_dir / content_path

        if not full_path.exists():
            raise FileNotFoundError(f"Help file not found: {full_path}")

        return full_path.read_text(encoding="utf-8")

    def _create_button(self) -> None:
        """Create the help button and dialog."""
        with ui.button(self.button_text, icon=self.icon, on_click=self._show_dialog).props(
            'flat round size=sm color="grey-7"'
        ).tooltip(copy_text("help.button.tooltip")):
            pass

    def _show_dialog(self) -> None:
        """Show the help dialog."""
        with ui.dialog() as dialog, ui.card().classes("w-full max-w-2xl max-h-[80vh]"):
            # Header
            with ui.row().classes("w-full items-center justify-between p-4 border-b"):
                ui.label(self.title).classes("text-lg font-bold")
                ui.button(icon="close", on_click=dialog.close).props("flat round size=sm")

            # Content (scrollable)
            with ui.scroll_area().classes("w-full p-4"):
                ui.markdown(self.content).classes("prose prose-sm max-w-none")

            # Footer
            with ui.row().classes("w-full justify-end p-4 border-t"):
                ui.button("Close", on_click=dialog.close).props("flat")

            dialog.open()
