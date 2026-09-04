"""Allow running guiskindose as a module or via the ``guiskindose`` console script.

Two equivalent entry points share this body:

- ``python -m guiskindose`` (guarded by ``if __name__ == "__main__":``).
- The ``[project.scripts] guiskindose = "guiskindose.__main__:cli"`` console script.
"""

import logging
import sys

from guiskindose.constants import RUN_ARGUMENTS_MODE_GUI
from guiskindose.debug import configure_logging
from guiskindose.dev_data import DEVELOPMENT_PARAMETERS
from guiskindose.main import (
    analyze_input_file,
    get_argument_parser,
    main,
    preview_input_file,
    run_cli_export,
    validate_export_flags,
)
from guiskindose.privacy import install_value_safe_excepthook, safe_user_error

logger = logging.getLogger(__name__)

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})


def cli() -> None:
    """Run the guiskindose CLI.

    Reads ``sys.argv`` and dispatches to the GUI, preview, export, or dose-calculation
    paths exactly like ``python -m guiskindose``. Exits the process via ``sys.exit``
    on invalid export combinations and on ``--input-preview-only`` without a file.
    """
    install_value_safe_excepthook(logger)
    args = get_argument_parser(sys.argv[1:])

    # Configure logging once for all entry paths. run_gui calls this again in
    # native mode to add a file sink; the call is idempotent.
    configure_logging()

    # Reject incompatible --export-format combinations before any branch runs.
    if getattr(args, "export_format", None):
        try:
            validate_export_flags(
                args.export_format,
                aggregate_only=getattr(args, "aggregate_only", False),
                input_preview_only=getattr(args, "input_preview_only", False),
                has_files=bool(args.file_path),
            )
        except ValueError:
            print(safe_user_error("invalid_export_options"), file=sys.stderr)
            sys.exit(1)

    if args.mode == RUN_ARGUMENTS_MODE_GUI:
        from guiskindose.gui.app import run_gui

        run_gui(
            native=getattr(args, "native", False),
            host=getattr(args, "host", None),
            allow_network=getattr(args, "allow_network", False),
        )
    elif getattr(args, "input_preview_only", False):
        if not args.file_path:
            print("--input-preview-only requires --file-path", file=sys.stderr)
            sys.exit(1)
        for single_path in args.file_path:
            preview_input_file(
                single_path,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
                include_sensitive_values=getattr(args, "include_sensitive_preview", False),
            )
    else:
        if (run_settings := args.settings) is None:
            logger.warning("No settings specified. Running with development parameters")
            run_settings = DEVELOPMENT_PARAMETERS

        file_paths_raw: list[str] = args.file_path or []

        from pathlib import Path

        file_paths: list[str] = []
        for fp in file_paths_raw:
            p = Path(fp)
            if not p.exists() and ("*" in str(p) or "?" in str(p)):
                file_paths.extend([str(x) for x in sorted(p.parent.glob(p.name))])
            else:
                file_paths.append(fp)

        export_format = getattr(args, "export_format", None)
        if export_format:
            try:
                validate_export_flags(
                    export_format,
                    aggregate_only=getattr(args, "aggregate_only", False),
                    input_preview_only=getattr(args, "input_preview_only", False),
                    has_files=bool(file_paths),
                )
            except ValueError:
                print(safe_user_error("invalid_export_options"), file=sys.stderr)
                sys.exit(1)
            run_cli_export(
                file_paths,
                run_settings,
                export_format,
                export_path=getattr(args, "export_path", None),
                export_title=getattr(args, "export_title", None),
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
                include_source_identifiers=getattr(args, "include_source_identifiers", False),
                force=getattr(args, "force", False),
                allow_ignored_checkout=getattr(args, "allow_ignored_checkout_output", False),
            )
            print("Report written successfully.")
        elif len(file_paths) > 1:
            from guiskindose.main import analyze_multiple_input_files

            result = analyze_multiple_input_files(
                file_paths,
                settings=run_settings,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
            )
            if getattr(args, "aggregate_only", False):
                print(f"{result.aggregate_psd:.4f}")
            else:
                import json as _json

                print(_json.dumps(result.to_dict()))
        elif len(file_paths) == 1:
            single_path = file_paths[0]
            if Path(single_path).suffix.lower() in _TABULAR_SUFFIXES:
                analyze_input_file(
                    single_path,
                    settings=run_settings,
                    input_schema=getattr(args, "input_schema", None),
                    sheet_name=getattr(args, "sheet_name", 0),
                )
            else:
                main(file_path=single_path, settings=run_settings)
        else:
            main(file_path=None, settings=run_settings)


if __name__ == "__main__":
    cli()
