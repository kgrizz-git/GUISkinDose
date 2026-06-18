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
        for single_path in args.file_path:
            preview_input_file(
                single_path,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
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

        if len(file_paths) > 1:
            from mypyskindose.main import analyze_multiple_input_files
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
