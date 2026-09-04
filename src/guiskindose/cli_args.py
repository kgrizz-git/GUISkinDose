"""CLI argument parser construction for guiskindose.

Extracted from ``main.py`` (Phase 4c) so ``main.py`` stays under the repo's
800-line ceiling. ``main.py`` and ``__main__`` re-export ``get_argument_parser``
from here to keep the public surface unchanged.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from guiskindose.cli_kerma_meter import add_kerma_meter_cli_arguments
from guiskindose.constants import RUN_ARGUMENTS_MODE_GUI, RUN_ARGUMENTS_MODE_HEADLESS


def get_argument_parser(arguments) -> argparse.Namespace:
    """Parse CLI argv into an argparse Namespace for guiskindose."""
    parser = argparse.ArgumentParser(
        prog="guiskindose",
        description=(
            "GUISkinDose is a Python 3.11+ program for patient peak skin dose"
            " (PSD) estimations and 3D skin dose maps from fluoroscopic procedures"
            " in interventional radiology. Accepts DICOM RDSR files (.dcm),"
            " pre-parsed JSON exports, or tabular event-table exports (.csv, .tsv, .xlsx)."
        ),
        epilog=(
            "Beam-miss warnings: events that deposit zero dose because the beam does "
            "not intersect the patient phantom are reported at WARNING level. "
            "In multi-exam mode, the per-event dial is downgraded to 'summary' "
            "(one summary per exam) with an INFO log on stderr."
        ),
    )
    _add_top_level_args(parser)
    _add_input_args(parser)
    _add_export_args(parser)
    _add_gui_args(parser)
    add_kerma_meter_cli_arguments(parser)
    return parser.parse_args(arguments)


def _add_top_level_args(parser: argparse.ArgumentParser) -> None:
    """Mode, file path(s), and settings — the always-available pull-args.

    ``--mode gui`` and its ``--native`` sibling stay top-level so
    ``python -m guiskindose --mode gui --native`` keeps working without a
    sub-command dispatch.
    """
    parser.add_argument(
        "--mode",
        "-m",
        dest="mode",
        choices=(RUN_ARGUMENTS_MODE_HEADLESS, RUN_ARGUMENTS_MODE_GUI),
        default=RUN_ARGUMENTS_MODE_HEADLESS,
    )

    parser.add_argument(
        "--file-path",
        "-f",
        required=False,
        nargs="+",
        dest="file_path",
        help=(
            "Path(s) to input file(s). Accepts one or more .dcm, .csv, .tsv, or .xlsx "
            "paths. Multiple paths are processed as separate exams. A single tabular "
            "file containing multiple study identifiers is automatically split."
        ),
    )

    parser.add_argument(
        "--settings",
        "-s",
        required=False,
        type=Path,
        default=None,
        dest="settings",
        help="Path to the settings file to use if a specific settings file is required",
    )

    parser.add_argument(
        "--native",
        action="store_true",
        default=False,
        dest="native",
        help="Open GUI in a native desktop window instead of a browser tab (requires pywebview)",
    )


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    """Schema/preview/aggregate selection for tabular input handling."""
    parser.add_argument(
        "--input-schema",
        required=False,
        default="auto",
        dest="input_schema",
        choices=("normalized", "generic_rdsr_like", "radimetrics", "dosetrack", "auto"),
        help=(
            "Schema adapter for tabular files (.csv/.tsv/.xlsx). Default: 'auto' "
            "(detect from column headers; falls back to an explicit choice if ambiguous)."
        ),
    )

    parser.add_argument(
        "--sheet-name",
        required=False,
        default=0,
        dest="sheet_name",
        help="Sheet name or 0-based index for Excel files (default: 0).",
    )

    parser.add_argument(
        "--input-preview-only",
        action="store_true",
        default=False,
        dest="input_preview_only",
        help="Print a value-safe input summary without running dose calculation.",
    )

    parser.add_argument(
        "--include-sensitive-preview",
        action="store_true",
        default=False,
        dest="include_sensitive_preview",
        help=(
            "Deprecated no-op retained for compatibility. Input preview never prints "
            "filenames, study IDs, warning text, or event values."
        ),
    )

    parser.add_argument(
        "--aggregate",
        action="store_true",
        default=False,
        dest="aggregate_only",
        help="In multi-exam mode: print only the aggregate PSD to stdout instead of the full JSON.",
    )


def _add_export_args(parser: argparse.ArgumentParser) -> None:
    """Rich audit report output flags (XLSX/PDF/HTML/DOCX)."""
    parser.add_argument(
        "--export-format",
        required=False,
        default=None,
        dest="export_format",
        choices=("xlsx", "pdf", "html", "docx"),
        help="Generate a Rich audit report (XLSX/PDF/HTML/DOCX) instead of printing JSON.",
    )

    parser.add_argument(
        "--export-path",
        required=False,
        default=None,
        dest="export_path",
        type=Path,
        help="Required output path for --export-format. Existing and tracked files are refused by default.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Allow replacement of an existing untracked export file.",
    )

    parser.add_argument(
        "--include-source-identifiers",
        action="store_true",
        default=False,
        help="Include source filenames in reports; the resulting file may contain PHI.",
    )

    parser.add_argument(
        "--allow-ignored-checkout-output",
        action="store_true",
        default=False,
        help="Allow export only to a Git-ignored path inside the current checkout.",
    )

    parser.add_argument(
        "--export-title",
        required=False,
        default=None,
        dest="export_title",
        help="Optional report title for --export-format.",
    )


def _add_gui_args(parser: argparse.ArgumentParser) -> None:
    """GUI server binding flags (--host/--allow-network; --native lives top-level)."""
    parser.add_argument(
        "--host",
        required=False,
        default=None,
        dest="host",
        help=(
            "Host/interface for the GUI server to bind to. Defaults to 127.0.0.1 "
            "(localhost only). Pass '0.0.0.0' to serve on the LAN — only on a "
            "trusted network, since the GUI has no authentication and exposes "
            "loaded PHI-derived data. Requires --allow-network."
        ),
    )

    parser.add_argument(
        "--allow-network",
        action="store_true",
        default=False,
        dest="allow_network",
        help=(
            "Explicitly acknowledge and allow a non-loopback GUI binding. The GUI "
            "has no authentication and may display PHI-derived data."
        ),
    )
