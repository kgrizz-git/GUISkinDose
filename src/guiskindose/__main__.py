"""Allow running guiskindose as a module or via the ``guiskindose`` console script.

Equivalent entry points share this body:

- ``python -m guiskindose`` (guarded by ``if __name__ == "__main__":``).
- ``python -m guiskindose.main`` (delegates here from ``main.py``).
- The ``[project.scripts] guiskindose = "guiskindose.__main__:cli"`` console script.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from guiskindose.cli_args import import_options_from_args
from guiskindose.constants import RUN_ARGUMENTS_MODE_GUI
from guiskindose.debug import configure_logging
from guiskindose.input_adapters.import_options import (
    TabularImportOptions,
    reject_import_options_for_non_tabular,
)
from guiskindose.main import (
    analyze_input_file,
    analyze_multiple_input_files,
    get_argument_parser,
    main,
    prepare_cli_settings,
    preview_input_file,
    print_cli_result,
    run_cli_export,
    validate_export_flags,
)
from guiskindose.privacy import UserFacingInputError, install_value_safe_excepthook, safe_user_error

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})


def _call_or_exit(action: Callable[[], Any]) -> Any:
    """Run *action* or print a value-safe input error and exit 1."""
    try:
        return action()
    except UserFacingInputError as exc:
        print(exc.user_message(), file=sys.stderr)
        sys.exit(1)


def _validate_export_or_exit(args: argparse.Namespace, *, has_files: bool) -> None:
    """Reject incompatible ``--export-format`` combinations before work starts."""
    export_format = getattr(args, "export_format", None)
    if not export_format:
        return
    try:
        validate_export_flags(
            export_format,
            aggregate_only=getattr(args, "aggregate_only", False),
            input_preview_only=getattr(args, "input_preview_only", False),
            has_files=has_files,
        )
    except ValueError:
        print(safe_user_error("invalid_export_options"), file=sys.stderr)
        sys.exit(1)


def _resolve_file_paths(file_paths_raw: list[str]) -> list[str]:
    """Expand glob-looking paths that do not already exist as files."""
    file_paths: list[str] = []
    for fp in file_paths_raw:
        p = Path(fp)
        if not p.exists() and ("*" in str(p) or "?" in str(p)):
            file_paths.extend([str(x) for x in sorted(p.parent.glob(p.name))])
        else:
            file_paths.append(fp)
    return file_paths


def _run_preview(args: argparse.Namespace, import_opts: TabularImportOptions) -> None:
    """Print value-safe previews for each ``--file-path``."""
    if not args.file_path:
        print("--input-preview-only requires --file-path", file=sys.stderr)
        sys.exit(1)
    preview_settings = prepare_cli_settings(args)

    def _preview_all() -> None:
        for single_path in args.file_path:
            preview_input_file(
                single_path,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
                include_sensitive_values=getattr(args, "include_sensitive_preview", False),
                settings=preview_settings,
                import_options=import_opts,
            )

    _call_or_exit(_preview_all)


def _run_export(
    args: argparse.Namespace,
    import_opts: TabularImportOptions,
    run_settings: Any,
    file_paths: list[str],
) -> None:
    """Write a Rich report from the resolved CLI file list."""

    def _export() -> None:
        run_cli_export(
            file_paths,
            run_settings,
            args.export_format,
            export_path=getattr(args, "export_path", None),
            export_title=getattr(args, "export_title", None),
            input_schema=getattr(args, "input_schema", None),
            sheet_name=getattr(args, "sheet_name", 0),
            include_source_identifiers=getattr(args, "include_source_identifiers", False),
            force=getattr(args, "force", False),
            allow_ignored_checkout=getattr(args, "allow_ignored_checkout_output", False),
            import_options=import_opts,
        )

    _call_or_exit(_export)
    print("Report written successfully.")


def _run_single_file(
    single_path: str,
    run_settings: Any,
    args: argparse.Namespace,
    import_opts: TabularImportOptions,
) -> None:
    """Analyze one tabular file or one RDSR/JSON file."""
    aggregate_only = getattr(args, "aggregate_only", False)
    if Path(single_path).suffix.lower() in _TABULAR_SUFFIXES:

        def _analyze_tabular() -> Any:
            return analyze_input_file(
                single_path,
                settings=run_settings,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
                import_options=import_opts,
            )

        print_cli_result(_call_or_exit(_analyze_tabular), aggregate_only=aggregate_only)
        return

    def _analyze_rdsr() -> Any:
        reject_import_options_for_non_tabular([single_path], import_opts)
        return main(file_path=single_path, settings=run_settings)

    print_cli_result(_call_or_exit(_analyze_rdsr), aggregate_only=aggregate_only)


def _run_headless(args: argparse.Namespace, import_opts: TabularImportOptions) -> None:
    """Dispatch export or dose calculation for non-GUI CLI invocations."""
    run_settings = prepare_cli_settings(args)
    file_paths = _resolve_file_paths(args.file_path or [])
    if getattr(args, "export_format", None):
        _validate_export_or_exit(args, has_files=bool(file_paths))
        _run_export(args, import_opts, run_settings, file_paths)
        return
    if len(file_paths) > 1:

        def _analyze_many() -> Any:
            return analyze_multiple_input_files(
                file_paths,
                settings=run_settings,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
                import_options=import_opts,
            )

        print_cli_result(
            _call_or_exit(_analyze_many),
            aggregate_only=getattr(args, "aggregate_only", False),
        )
        return
    if len(file_paths) == 1:
        _run_single_file(file_paths[0], run_settings, args, import_opts)
        return
    print_cli_result(main(file_path=None, settings=run_settings))


def cli() -> None:
    """Run the guiskindose CLI.

    Reads ``sys.argv`` and dispatches to the GUI, preview, export, or dose-calculation
    paths exactly like ``python -m guiskindose``. Exits the process via ``sys.exit``
    on invalid export combinations and on ``--input-preview-only`` without a file.
    """
    install_value_safe_excepthook(logger)
    args = get_argument_parser(sys.argv[1:])
    import_opts = import_options_from_args(args)

    # Configure logging once for all entry paths. run_gui calls this again in
    # native mode to add a file sink; the call is idempotent.
    configure_logging()

    # Reject incompatible --export-format combinations before any branch runs.
    _validate_export_or_exit(args, has_files=bool(args.file_path))

    if args.mode == RUN_ARGUMENTS_MODE_GUI:
        from guiskindose.gui.app import run_gui

        run_gui(
            native=getattr(args, "native", False),
            port=getattr(args, "port", None),
        )
        return
    if getattr(args, "input_preview_only", False):
        _run_preview(args, import_opts)
        return
    _run_headless(args, import_opts)


if __name__ == "__main__":
    cli()
