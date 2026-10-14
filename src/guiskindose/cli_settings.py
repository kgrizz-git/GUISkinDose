"""Headless CLI settings preparation for guiskindose.

Extracted from ``main.py`` so ``main.py`` stays under the repo's 800-line
ceiling. ``main.py`` re-exports ``prepare_cli_settings`` to keep the public
surface unchanged.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from guiskindose.cli_kerma_meter import apply_kerma_meter_cli_flags
from guiskindose.dev_data import DEVELOPMENT_PARAMETERS
from guiskindose.equipment_profiles.errors import EquipmentProfileError
from guiskindose.helpers.parse_settings_to_settings_class import (
    parse_settings_to_settings_class,
)
from guiskindose.privacy import UserFacingInputError, safe_user_error
from guiskindose.settings import PyskindoseSettings

if TYPE_CHECKING:
    import argparse

    from guiskindose.settings_equipment_profiles import _ValidatedRequest

logger = logging.getLogger(__name__)

GUI_SETTINGS_EQUIPMENT_PROFILES_MESSAGE = (
    "Equipment profile sources in settings files apply only to headless runs, "
    "not --mode gui."
)


def _settings_base_dir(raw: Any, args: Any) -> Path | None:
    """Capture the settings-file parent before reading (pure; no filesystem touch).

    Without profile flags this never raises (legacy-exact); with flags, hostile
    path hooks fail closed here rather than silently falling back to the working
    directory. `KeyboardInterrupt` and `SystemExit` always propagate.
    """
    from guiskindose.cli_equipment_profiles import equipment_profile_args_present

    try:
        if isinstance(raw, Path):
            return raw.parent
        if isinstance(raw, str) and not raw.lstrip().startswith("{"):
            return Path(raw).parent
        return None
    except Exception:
        if equipment_profile_args_present(args):
            raise UserFacingInputError("Equipment profile settings path is not valid.") from None
        return None


def _extract_profile_block(raw: Any) -> tuple[Any | None, Any]:
    """Split an optional equipment_profiles block off raw settings without mutating it.

    Dict inputs are transiently copied with the block removed; JSON strings
    are probed read-only and decode failures proceed legacy-exact (the legacy
    construction fallback still owns malformed JSON); everything else passes
    through with no block. Returns (block_or_None, working_input).
    """
    if isinstance(raw, dict):
        try:
            working = dict(raw)
        except Exception:
            # Hostile mapping hooks: fall back to legacy-exact handling of the
            # untouched input rather than leaking hook errors.
            return None, raw
        return working.pop("equipment_profiles", None), working
    if isinstance(raw, str) and raw.lstrip().startswith("{"):
        from guiskindose.settings_equipment_profiles import split_json_block

        try:
            return split_json_block(raw)
        except EquipmentProfileError:
            raise UserFacingInputError("Equipment profile settings are not valid.") from None
        except ValueError:
            return None, raw
    return None, raw


def _profile_requests(
    args: Any, block: Any | None, base: Path | None
) -> tuple[_ValidatedRequest | None, _ValidatedRequest | None]:
    """Parse CLI and config sides purely; the caller converts failures closed.

    The base validates first; both sides then parse fully, and the combined
    file-plus-snapshot total validates before any settings construction,
    mutation, or profile/store I/O. Raises EquipmentProfileError (converted
    once at the single CLI boundary); UserFacingInputError passes through
    untouched.
    """
    from guiskindose.cli_equipment_profiles import _cli_request_from_args
    from guiskindose.settings_equipment_profiles import (
        _check_composed_bounds,
        _parse_request,
        _validated_base,
    )

    resolved_base = _validated_base(base)
    cli_request = _cli_request_from_args(args)
    config_request = None if block is None else _parse_request(block, resolved_base)
    _check_composed_bounds(cli_request, config_request)
    return cli_request, config_request


def _validated_profile_inputs(
    args: Any, raw: Any, base: Path | None
) -> tuple[Any, _ValidatedRequest | None, _ValidatedRequest | None]:
    """Extract and validate profile inputs under the value-free CLI converter."""
    try:
        block, working = _extract_profile_block(raw)
        cli_request, config_request = _profile_requests(args, block, base)
    except EquipmentProfileError as exc:
        raise UserFacingInputError(str(exc)) from None
    return working, cli_request, config_request


def _assemble_and_bind(
    settings: PyskindoseSettings,
    cli_request: _ValidatedRequest | None,
    config_request: _ValidatedRequest | None,
) -> None:
    """Assemble both sides once and bind last; no-op unless a side is present."""
    from guiskindose.cli_equipment_profiles import bind_equipment_session
    from guiskindose.settings_equipment_profiles import _assemble_composed

    if cli_request is None and config_request is None:
        return
    try:
        session = _assemble_composed(cli_request, config_request)
    except EquipmentProfileError as exc:
        raise UserFacingInputError(str(exc)) from None
    bind_equipment_session(settings, session)


def settings_equipment_block_present(args: Any) -> bool:
    """Inspect-only check whether CLI settings carry an equipment_profiles block.

    Reads the chosen settings file (never echoed); any read/parse problem
    means proceed legacy (GUI ignores settings today). Inline JSON strings
    are probed the same way. Never assembles anything; programmatic objects
    and dicts are not inspected here.
    """
    raw = getattr(args, "settings", None)
    text: str | None = None
    if isinstance(raw, Path):
        try:
            text = raw.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
    elif isinstance(raw, str) and not raw.lstrip().startswith("{"):
        try:
            if not Path(raw).is_file():
                return False
            text = Path(raw).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return False
    elif isinstance(raw, str):
        text = raw
    else:
        return False
    try:
        parsed = json.loads(text)
    except ValueError:
        return False
    return isinstance(parsed, dict) and parsed.get("equipment_profiles") is not None


def prepare_cli_settings(args: argparse.Namespace) -> PyskindoseSettings:
    """Build the run settings for a headless CLI invocation, shared by both entry points.

    ``--settings`` may be a path to a JSON file or a JSON string (a path is read,
    never echoed). With no ``--settings`` the development parameters are used. A
    settings file's parent directory anchors relative equipment-profile source
    paths; inline JSON/dict configs resolve against the working directory, as do
    CLI flag paths. CLI flags and the settings ``equipment_profiles`` block compose
    into one candidate assembled once and bound last; an invalid block fails closed
    before the legacy construction fallback can swallow it. The kerma-meter flags
    (including ``--kerma-meter-calibration-date``) and ``--plane-code-map`` are then
    applied onto the concrete settings object.

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
    from guiskindose.cli_equipment_profiles import equipment_profile_args_present

    if (
        isinstance(raw, PyskindoseSettings)
        and getattr(raw, "equipment_profile_session", None) is not None
        and equipment_profile_args_present(args)
    ):
        raise UserFacingInputError("Equipment profile session is already configured.")
    base = _settings_base_dir(raw, args)
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
    working, cli_request, config_request = _validated_profile_inputs(args, raw, base)
    settings = parse_settings_to_settings_class(settings=working)
    has_sources = cli_request is not None or config_request is not None
    if has_sources and isinstance(raw, PyskindoseSettings):
        # Caller-owned home with configured sources: stage every later change
        # on an isolated private copy, so a kerma/plane/profile failure leaves
        # the caller's config, normalization, output format, and session intact.
        from guiskindose.equipment_captured_input import shielded_settings_for_capture

        settings = shielded_settings_for_capture(settings)
    if getattr(args, "output_format", None):
        settings.output_format = args.output_format
    apply_kerma_meter_cli_flags(settings, args)
    plane_code_map_raw = getattr(args, "plane_code_map", None)
    if plane_code_map_raw is not None:
        from guiskindose.input_adapters.plane_code_map import parse_plane_code_map

        settings.dosetrack_plane_code_map = parse_plane_code_map(plane_code_map_raw)
    _assemble_and_bind(settings, cli_request, config_request)
    return settings
