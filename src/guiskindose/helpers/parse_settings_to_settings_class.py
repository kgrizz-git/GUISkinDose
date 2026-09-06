"""Coerce settings input into a :class:`PyskindoseSettings` instance.

Falls back to the bundled ``settings_example.json`` when no input is
provided.
"""
import logging
from pathlib import Path

from guiskindose.settings import PyskindoseSettings, initialize_settings

logger = logging.getLogger(__name__)


def parse_settings_to_settings_class(
    settings: str | dict | PyskindoseSettings | None = None,
) -> PyskindoseSettings:
    """Return a validated :class:`PyskindoseSettings` from supported input types.

    Parameters
    ----------
    settings : str | dict | PyskindoseSettings | None, optional
        JSON string, dict, or existing settings object. When *None*, the
        bundled ``settings_example.json`` is used.

    Returns
    -------
    PyskindoseSettings
        Parsed and initialized settings object.

    """
    if settings is not None:
        try:
            return initialize_settings(settings)
        except ValueError:
            logger.debug("Tried initializing settings without any settings")

    settings_path = Path(__file__).parent.parent / "settings.json"

    if not settings_path.exists():
        logger.warning("Settings path not specified. Using example settings.")
        settings_path = settings_path.parent / "settings_example.json"

    return PyskindoseSettings(settings_path.read_text())
