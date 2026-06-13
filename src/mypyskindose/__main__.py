"""Allow running mypyskindose as a module: python -m mypyskindose"""

import logging
import sys

from mypyskindose.constants import RUN_ARGUMENTS_MODE_GUI
from mypyskindose.debug import configure_logging
from mypyskindose.dev_data import DEVELOPMENT_PARAMETERS
from mypyskindose.main import analyze_input_file, get_argument_parser, main, preview_input_file

logger = logging.getLogger(__name__)

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

if __name__ == "__main__":
    args = get_argument_parser(sys.argv[1:])

    # Configure logging once for all entry paths. run_gui calls this again in
    # native mode to add a file sink; the call is idempotent.
    configure_logging()

    if args.mode == RUN_ARGUMENTS_MODE_GUI:
        from mypyskindose.gui.app import run_gui

        run_gui(native=getattr(args, "native", False), host=getattr(args, "host", None))
    elif getattr(args, "input_preview_only", False):
        if not args.file_path:
            print("--input-preview-only requires --file-path", file=sys.stderr)
            sys.exit(1)
        preview_input_file(
            args.file_path,
            input_schema=getattr(args, "input_schema", None),
            sheet_name=getattr(args, "sheet_name", 0),
        )
    else:
        if (run_settings := args.settings) is None:
            logger.warning("No settings specified. Running with development parameters")
            run_settings = DEVELOPMENT_PARAMETERS

        file_path = args.file_path
        input_schema = getattr(args, "input_schema", None)
        sheet_name = getattr(args, "sheet_name", 0)

        from pathlib import Path

        if file_path and Path(file_path).suffix.lower() in _TABULAR_SUFFIXES:
            analyze_input_file(
                file_path,
                settings=run_settings,
                input_schema=input_schema,
                sheet_name=sheet_name,
            )
        else:
            main(file_path=file_path, settings=run_settings)
