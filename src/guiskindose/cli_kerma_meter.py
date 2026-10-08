"""CLI wiring for kerma-meter correction flags."""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from guiskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def add_kerma_meter_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """Register ``--kerma-meter-*`` flags on *parser*."""
    parser.add_argument(
        "--kerma-meter-correction",
        action="store_true",
        default=False,
        dest="kerma_meter_correction",
        help="Enable kerma-meter correction factors (per equipment × tube).",
    )
    parser.add_argument(
        "--kerma-meter-correction-file",
        required=False,
        default=None,
        type=Path,
        dest="kerma_meter_correction_file",
        help="Path to kerma-meter CF lookup table (CSV/TSV/XLSX/JSON).",
    )
    parser.add_argument(
        "--kerma-meter-correction-mode",
        required=False,
        default=None,
        choices=("file", "prompt"),
        dest="kerma_meter_correction_mode",
        help=(
            "DEPRECATED. The file always loads when --kerma-meter-correction-file is set; "
            "manual entries win over it, then default_factor. 'prompt' maps to "
            "ask_for_missing (GUI-only; CLI never prompts)."
        ),
    )
    parser.add_argument(
        "--kerma-meter-calibration-date",
        required=False,
        default=None,
        type=_iso_date,
        dest="kerma_meter_calibration_date",
        metavar="YYYY-MM-DD",
        help=(
            "Pick the calibration period containing this date from a calibration file with "
            "valid_from / valid_to columns, for every exam. Without it the current period "
            "(no valid_to), else the most recent, is used and a count-only warning is logged."
        ),
    )
    parser.add_argument(
        "--kerma-meter-explicit-label",
        required=False,
        default=None,
        dest="kerma_meter_explicit_label",
        help="Force all events to this equipment label for CF lookup.",
    )


def _iso_date(text: str) -> date:
    """argparse type: an ISO ``YYYY-MM-DD`` date."""
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an ISO date, YYYY-MM-DD") from exc


def apply_kerma_meter_cli_flags(settings: PyskindoseSettings, args: argparse.Namespace) -> None:
    """Map CLI kerma-meter flags onto ``settings.kerma_meter_correction``."""
    km = settings.kerma_meter_correction
    if getattr(args, "kerma_meter_correction", False):
        km.enable = True
    file_path = getattr(args, "kerma_meter_correction_file", None)
    if file_path is not None:
        km.enable = True
        km.file = Path(file_path)
    mode = getattr(args, "kerma_meter_correction_mode", None)
    if mode is not None:
        km.apply_legacy_mode(mode)
    calibration_date = getattr(args, "kerma_meter_calibration_date", None)
    if calibration_date is not None:
        km.calibration_date = calibration_date
    label = getattr(args, "kerma_meter_explicit_label", None)
    if label is not None:
        km.explicit_label = str(label)
