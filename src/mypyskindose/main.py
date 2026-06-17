import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import pandas as pd

from mypyskindose.analyze_data import analyze_data, analyze_multiple_exams
from mypyskindose.constants import (
    RUN_ARGUMENTS_MODE_GUI,
    RUN_ARGUMENTS_MODE_HEADLESS,
    RUN_ARGUMENTS_OUTPUT_DICT,
    RUN_ARGUMENTS_OUTPUT_HTML,
    RUN_ARGUMENTS_OUTPUT_JSON,
)
from mypyskindose.debug import dprint
from mypyskindose.dev_data import DEVELOPMENT_PARAMETERS
from mypyskindose.format_export_data import MultiExamResult, PySkinDoseOutput
from mypyskindose.helpers.parse_settings_to_settings_class import (
    parse_settings_to_settings_class,
)
from mypyskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from mypyskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})


def main(
    file_path: Optional[str] = None,
    settings: Optional[Union[str, dict, PyskindoseSettings]] = None,
):
    """Run PySkinDose.

    Copy settings_examples.json and save it as settings.json.
    Set all you parameters in this file. For debugging and developement,
    the PARAM_dev settings dictionary can be used by calling
    main(settings=PARAM_DEV).

    See settings.py for a description of all the parameters. Please visit
    https://github.com/rvbCMTS/PySkinDose for info on how to run
    PySkinDose.

    Parameters
    ----------
    file_path : str, optional
        file path to RDSR file or preparsed RDSR data in .json format
    settings : Union[str, dict, PyskindoseSettings], optional
        Setting file in either dict, json string format, or as a
        PyskindoseSettings object. By default, settings_examples.json is
        enabled.

    """
    settings = parse_settings_to_settings_class(settings=settings)

    # Don't log file_path — RDSR paths/filenames can carry PHI.
    dprint("PROCESSING", "Reading and normalizing RDSR data")
    data_norm = read_and_normalise_rdsr_data(rdsr_filepath=file_path, settings=settings)
    dprint("PROCESSING", f"RDSR data normalized successfully. Rows: {len(data_norm)}")

    dprint("PROCESSING", "Calling analyze_data")
    output = analyze_data(normalized_data=data_norm, settings=settings)
    dprint("PROCESSING", "analyze_data finished")

    if settings.output_format in ("dict", "json"):
        return output

def analyze_input_file(
    file_path: str | Path,
    settings: Optional[Union[str, dict, PyskindoseSettings]] = None,
    *,
    input_schema: Optional[str] = None,
    sheet_name: Union[str, int] = 0,
    output_format: str = RUN_ARGUMENTS_OUTPUT_DICT,
) -> Any:
    """Run PySkinDose from a tabular file (.csv, .tsv, .xlsx) or DICOM/JSON.

    For tabular files the input_adapters registry handles loading and
    column mapping. DICOM and JSON files fall through to the existing path.

    Parameters
    ----------
    file_path:
        Path to the input file.
    settings:
        Settings as a dict, JSON string, path, or PyskindoseSettings object.
    input_schema:
        Schema adapter name for tabular files ("normalized"). Pass None to use
        the default. "auto" is not yet supported.
    sheet_name:
        Sheet name or 0-based index for Excel files (ignored otherwise).
    output_format:
        "dict" (default), "json", or "html".
    """
    settings = parse_settings_to_settings_class(settings=settings)
    settings.output_format = output_format.casefold()

    suffix = Path(file_path).suffix.lower()

    if suffix in _TABULAR_SUFFIXES:
        from mypyskindose.input_adapters.registry import read_and_normalize_input

        result = read_and_normalize_input(
            file_path,
            input_schema=input_schema,
            sheet_name=sheet_name,
            settings=settings,
        )
        if isinstance(result, list):
            for exam in result:
                for w in exam.warnings:
                    logger.warning("tabular input (exam %s): %s", exam.study_id or "?", w)
            return analyze_multiple_exams(result, settings)
        for w in result.warnings:
            logger.warning("tabular input: %s", w)
        data_norm = result.normalized_data
    else:
        data_norm = read_and_normalise_rdsr_data(rdsr_filepath=str(file_path), settings=settings)

    return analyze_data(normalized_data=data_norm, settings=settings)


def analyze_multiple_input_files(
    file_paths: Sequence[str | Path],
    settings: Optional[Union[str, dict, PyskindoseSettings]] = None,
    *,
    input_schema: Optional[str] = None,
    sheet_name: Union[str, int] = 0,
    per_exam_offsets: list[list[float]] | None = None,
) -> MultiExamResult:
    """Run PySkinDose on a list of input files, treating each as a separate exam.

    Tabular files that contain multiple study identifiers are automatically split
    into per-exam inputs before processing.  RDSR / JSON files are each treated
    as one exam.

    Parameters
    ----------
    file_paths:
        Paths to input files (.csv, .tsv, .xlsx, .dcm, .json). Glob patterns
        (e.g. ``"exams/*.dcm"``) should be expanded by the caller before passing.
    settings:
        Global settings applied to all exams.
    input_schema:
        Schema adapter for tabular files. ``None`` defaults to ``"normalized"``.
    sheet_name:
        Sheet name or 0-based index for Excel files.
    per_exam_offsets:
        Optional per-exam patient offsets [[d_lon, d_ver, d_lat], ...].
    """
    from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    settings_obj = parse_settings_to_settings_class(settings=settings)
    all_exams: list[InputAdapterResult] = []

    for fp in file_paths:
        fp = Path(fp)
        suffix = fp.suffix.lower()
        if suffix in _TABULAR_SUFFIXES:
            result = read_and_normalize_input(
                fp, input_schema=input_schema, sheet_name=sheet_name, settings=settings_obj
            )
            if isinstance(result, list):
                all_exams.extend(result)
            else:
                all_exams.append(result)
        else:
            data_norm = read_and_normalise_rdsr_data(rdsr_filepath=str(fp), settings=settings_obj)
            provenance = InputProvenance(
                source_type=suffix.lstrip("."),
                schema_name="rdsr",
                original_filename=fp.name,
                header_row_index=0,
                detected_encoding="n/a",
                detected_delimiter=None,
                sheet_name=None,
                column_map={},
                unit_conversions={},
                warnings=[],
            )
            all_exams.append(
                InputAdapterResult(
                    normalized_data=data_norm,
                    raw_data=None,
                    provenance=provenance,
                    warnings=[],
                )
            )

    return analyze_multiple_exams(all_exams, settings_obj, per_exam_offsets=per_exam_offsets)


def preview_input_file(
    file_path: str | Path,
    *,
    input_schema: Optional[str] = None,
    sheet_name: Union[str, int] = 0,
) -> None:
    """Print a column-mapping preview without running the dose calculation."""
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    raw = read_and_normalize_input(
        file_path,
        input_schema=input_schema,
        sheet_name=sheet_name,
    )
    results = raw if isinstance(raw, list) else [raw]
    for result in results:
        prov = result.provenance
        print(f"File:          {prov.original_filename}")
        if result.study_id:
            print(f"Study ID:      {result.study_id}")
        print(f"Schema:        {prov.schema_name}")
        print(f"Encoding:      {prov.detected_encoding}")
        print(f"Delimiter:     {prov.detected_delimiter!r}")
        print(f"Header row:    {prov.header_row_index}")
        print(f"Events loaded: {len(result.normalized_data)}")
        print()
        print("Column map (source → normalized):")
        for src, norm in prov.column_map.items():
            print(f"  {src!r:30s} → {norm}")
        if prov.warnings:
            print()
            print("Warnings:")
            for w in prov.warnings:
                print(f"  {w}")
        print()
        print("First 5 normalized events:")
        print(result.normalized_data.head(5).to_string())
        print()


def analyze_normalized_data_with_custom_settings_object(
    data_norm: pd.DataFrame,
    settings: Union[PyskindoseSettings, str, dict],
    output_format: Optional[str] = RUN_ARGUMENTS_OUTPUT_JSON,
) -> Union[str, dict[str, Any], PySkinDoseOutput]:
    """Run PySkinDose with custom normalized data and a custom specified settings objects.

    See the

    Parameters
    ----------
    data_norm : pd.DataFrame
        A pandas DataFrame containing the normalized data
    settings : Union[PySkinDoseSettings, str, dict]
        The settings for the PySkinDose analysis given as a PySKinDoseSettings object, a json-formatted string or a dict
    output_format : str, optional
        String specifying the output format. Valid values are "json"(default) and "dict"
    """
    if not isinstance(settings, (PyskindoseSettings, str, dict)):
        raise TypeError("Invalid type for input settings")

    if not isinstance(output_format, str) or output_format.casefold() not in [
        RUN_ARGUMENTS_OUTPUT_JSON,
        RUN_ARGUMENTS_OUTPUT_DICT,
        RUN_ARGUMENTS_OUTPUT_HTML,
    ]:
        raise ValueError(
            f"The output_format must be specified as a string with one of the valid values {RUN_ARGUMENTS_OUTPUT_JSON} "
            f"or {RUN_ARGUMENTS_OUTPUT_DICT}"
        )

    settings = parse_settings_to_settings_class(settings=settings)
    settings.output_format = output_format.casefold()

    dprint("PROCESSING", "Calling analyze_data from analyze_normalized_data_with_custom_settings_object")
    return analyze_data(normalized_data=data_norm, settings=settings)


def get_argument_parser(arguments) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="PySkinDose",
        description=(
            "PySkinDose is a Python version 3.8 based program for patient peak"
            " skin dose (PSD) estimations from fluoroscopic procedures in"
            " interventional radiology."
        ),
    )
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

    parser.add_argument(
        "--host",
        required=False,
        default=None,
        dest="host",
        help=(
            "Host/interface for the GUI server to bind to. Defaults to 127.0.0.1 "
            "(localhost only). Pass '0.0.0.0' to serve on the LAN — only on a "
            "trusted network, since the GUI has no authentication and exposes "
            "loaded PHI-derived data."
        ),
    )

    parser.add_argument(
        "--input-schema",
        required=False,
        default=None,
        dest="input_schema",
        choices=("normalized", "generic_rdsr_like", "radimetrics", "dosetrack", "auto"),
        help="Schema adapter for tabular files (.csv/.tsv/.xlsx). Default: 'normalized'.",
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
        help="Print column mapping and first events without running dose calculation.",
    )

    return parser.parse_args(arguments)


if __name__ == "__main__":
    args = get_argument_parser(sys.argv[1:])

    if args.mode == RUN_ARGUMENTS_MODE_GUI:
        from mypyskindose.gui.app import run_gui
        run_gui(native=getattr(args, "native", False), host=getattr(args, "host", None))
    else:
        if (run_settings := args.settings) is None:
            logger.warning("No settings specified. Running with development parameters")
            run_settings = DEVELOPMENT_PARAMETERS

        file_paths: list[str] = args.file_path or []
        if len(file_paths) > 1:
            result = analyze_multiple_input_files(
                file_paths,
                settings=run_settings,
                input_schema=getattr(args, "input_schema", None),
                sheet_name=getattr(args, "sheet_name", 0),
            )
            import json as _json
            print(_json.dumps(result.to_dict()))
        elif len(file_paths) == 1:
            single_path = file_paths[0]
            suffix = Path(single_path).suffix.lower()
            if suffix in _TABULAR_SUFFIXES:
                if getattr(args, "input_preview_only", False):
                    preview_input_file(
                        single_path,
                        input_schema=getattr(args, "input_schema", None),
                        sheet_name=getattr(args, "sheet_name", 0),
                    )
                else:
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
