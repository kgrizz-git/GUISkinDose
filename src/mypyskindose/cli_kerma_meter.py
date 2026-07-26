"""CLI wiring for kerma-meter correction flags."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mypyskindose.settings import PyskindoseSettings

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
        help="CF resolution mode. 'prompt' is GUI-only; CLI falls soft to default_factor.",
    )
    parser.add_argument(
        "--kerma-meter-explicit-label",
        required=False,
        default=None,
        dest="kerma_meter_explicit_label",
        help="Force all events to this equipment label for CF lookup.",
    )


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
        km.mode = mode
        if mode == "prompt":
            logger.warning(
                "kerma-meter correction: mode=prompt is GUI-only; "
                "CLI will use default_factor without blocking."
            )
    label = getattr(args, "kerma_meter_explicit_label", None)
    if label is not None:
        km.explicit_label = str(label)
