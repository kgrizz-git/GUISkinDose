"""Headless CLI settings preparation for guiskindose.

Extracted from ``main.py`` so ``main.py`` stays under the repo's 800-line
ceiling. ``main.py`` re-exports ``prepare_cli_settings`` to keep the public
surface unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from guiskindose.cli_kerma_meter import apply_kerma_meter_cli_flags
from guiskindose.dev_data import DEVELOPMENT_PARAMETERS
from guiskindose.helpers.parse_settings_to_settings_class import (
    parse_settings_to_settings_class,
)
from guiskindose.privacy import UserFacingInputError, safe_user_error
from guiskindose.settings import PyskindoseSettings

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)


def prepare_cli_settings(args: argparse.Namespace) -> PyskindoseSettings:
    """Build the run settings for a headless CLI invocation, shared by both entry points.

    ``--settings`` may be a path to a JSON file or a JSON string (a path is read,
    never echoed). With no ``--settings`` the development parameters are used. The
    kerma-meter flags (including ``--kerma-meter-calibration-date``) and
    ``--plane-code-map`` are then applied onto the concrete settings object.
    ``--equipment-profile`` files assemble one candidate session through the
    canonical file path and bind it last, before any exam input is read; a
    failed candidate raises without mutating settings, and an already-bound
    runtime session is never replaced silently. With profile flags set, an
    existing bound session is refused before any settings change or profile
    read, and caller-owned settings stage on an isolated private copy so a
    later failure leaves the caller's object intact. Without profile flags
    the legacy flow is unchanged.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    PyskindoseSettings
        Settings ready for ``main()`` / the analyze helpers.

    Raises
    ------
    SystemExit
        If ``--settings`` names a file that does not exist. The message never
        contains the path.
    """
    raw = args.settings
    if raw is None:
        logger.warning("No settings specified. Running with development parameters")
        raw = DEVELOPMENT_PARAMETERS
    elif isinstance(raw, Path) or (isinstance(raw, str) and not raw.lstrip().startswith("{")):
        # A path (or a string that is not a JSON object): read it, or fail cleanly.
        try:
            is_file = Path(raw).is_file()
        except OSError:
            is_file = False
        if not is_file:
            raise SystemExit(safe_user_error("settings_file_not_found"))
        raw = Path(raw).read_text(encoding="utf-8")
    settings = parse_settings_to_settings_class(settings=raw)
    settings = _stage_profile_settings(args, settings, raw)
    if getattr(args, "output_format", None):
        settings.output_format = args.output_format
    apply_kerma_meter_cli_flags(settings, args)
    plane_code_map_raw = getattr(args, "plane_code_map", None)
    if plane_code_map_raw is not None:
        from guiskindose.input_adapters.plane_code_map import parse_plane_code_map

        settings.dosetrack_plane_code_map = parse_plane_code_map(plane_code_map_raw)
    _bind_profile_session(args, settings)
    return settings


def _stage_profile_settings(args: Any, settings: PyskindoseSettings, raw: Any) -> PyskindoseSettings:
    """Refuse pre-bound sessions, then stage caller-owned homes on an isolated copy.

    Runs before any settings mutation or profile read when profile flags are
    set; without flags the settings object passes through untouched.
    """
    from guiskindose.cli_equipment_profiles import equipment_profile_args_present
    from guiskindose.equipment_captured_input import shielded_settings_for_capture

    if not equipment_profile_args_present(args):
        return settings
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise UserFacingInputError("Equipment profile session is already configured.")
    if isinstance(raw, PyskindoseSettings):
        # Caller-owned home with new flags: stage every later change on an
        # isolated private copy, so a kerma/plane/profile failure leaves the
        # caller's config, normalization, output format, and session intact.
        return shielded_settings_for_capture(settings)
    return settings


def _bind_profile_session(args: Any, settings: PyskindoseSettings) -> None:
    """Assemble the candidate session and bind it; no-op without profile flags."""
    from guiskindose.cli_equipment_profiles import (
        bind_equipment_session,
        equipment_profile_args_present,
        equipment_session_from_args,
    )

    if not equipment_profile_args_present(args):
        return
    bind_equipment_session(settings, equipment_session_from_args(args))
