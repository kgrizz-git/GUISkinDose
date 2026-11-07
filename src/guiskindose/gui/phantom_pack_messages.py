"""User-facing phantom pack sentences for CLI/GUI entry points."""

from __future__ import annotations

from guiskindose.gui.ui_copy import copy_text


def gui_mode_phantom_pack_refusal() -> str:
    """Sentence printed when ``--install-phantom-pack`` is passed with ``--mode gui``."""
    return copy_text("cli.phantom_pack.gui_mode_refusal")
