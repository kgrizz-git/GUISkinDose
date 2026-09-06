"""Entry point and CLI orchestration for GUISkinDose."""

import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from guiskindose.analyze_data import analyze_data, analyze_multiple_exams
from guiskindose.cli_args import get_argument_parser as _cli_args_get_argument_parser
from guiskindose.cli_kerma_meter import apply_kerma_meter_cli_flags
from guiskindose.constants import (
    RUN_ARGUMENTS_MODE_GUI,
    RUN_ARGUMENTS_OUTPUT_DICT,
    RUN_ARGUMENTS_OUTPUT_HTML,
    RUN_ARGUMENTS_OUTPUT_JSON,
)
from guiskindose.debug import dprint
from guiskindose.dev_data import DEVELOPMENT_PARAMETERS
from guiskindose.format_export_data import MultiExamResult, PySkinDoseOutput
from guiskindose.helpers.parse_settings_to_settings_class import (
    parse_settings_to_settings_class,
)
from guiskindose.helpers.read_and_normalize_rdsr_data import read_and_normalise_rdsr_data
from guiskindose.privacy import install_value_safe_excepthook, opaque_exam_label, safe_user_error, safe_warning
from guiskindose.settings import PyskindoseSettings

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})


def _settings_with_output_format(
    settings: str | dict | PyskindoseSettings | None, output_format: str
) -> PyskindoseSettings:
    """Parse settings and force the requested output_format."""
    settings_obj = parse_settings_to_settings_class(settings=settings)
    settings_obj.output_format = output_format.casefold()
    return settings_obj


def _warn_for_tabular_input(result: Any) -> None:
    """Log privacy-safe warning counts for one or more tabular input results."""
    results = result if isinstance(result, list) else [result]
    for index, exam in enumerate(results):
        if exam.warnings:
            fields = {"count": len(exam.warnings)}
            if isinstance(result, list):
                fields["exam"] = index + 1
            safe_warning(logger, "tabular_input_warnings", **fields)


def _read_input_for_analysis(
    file_path: str | Path,
    settings: PyskindoseSettings,
    input_schema: str | None,
    sheet_name: str | int,
) -> Any:
    """Load either a tabular input through its adapter or a legacy RDSR/JSON input."""
    if Path(file_path).suffix.lower() not in _TABULAR_SUFFIXES:
        return read_and_normalise_rdsr_data(rdsr_filepath=str(file_path), settings=settings)

    from guiskindose.input_adapters.registry import read_and_normalize_input

    return read_and_normalize_input(
        file_path,
        input_schema=input_schema,
        sheet_name=sheet_name,
        settings=settings,
    )


def _analysis_output_for_input(
    input_result: Any,
    settings: PyskindoseSettings,
    requested_output_format: str,
) -> Any:
    """Calculate a single normalized input or aggregate a multi-exam input."""
    if isinstance(input_result, pd.DataFrame):
        return analyze_data(normalized_data=input_result, settings=settings)
    if not isinstance(input_result, list):
        return analyze_data(normalized_data=input_result.normalized_data, settings=settings)

    if requested_output_format == RUN_ARGUMENTS_OUTPUT_HTML:
        logger.warning("HTML output format is not supported for multi-exam tabular runs. Forcing to dict.")
        settings.output_format = RUN_ARGUMENTS_OUTPUT_DICT
    return analyze_multiple_exams(input_result, settings)


def _print_input_preview(result: Any, exam_index: int, include_sensitive_values: bool) -> None:
    """Print one tabular-input preview with schema metadata and aggregate counts only.

    Never emits source filenames, study IDs, warning text, absolute paths, or
    normalized event values — including when ``include_sensitive_values`` is true.
    That flag is retained for CLI compatibility and only acknowledges the request.
    """
    del include_sensitive_values  # retained for callers; never enables identifier output
    provenance = result.provenance
    print(f"Exam:          {opaque_exam_label(exam_index)}")
    print(f"Schema:        {provenance.schema_name}")
    print(f"Encoding:      {provenance.detected_encoding}")
    print(f"Delimiter:     {provenance.detected_delimiter!r}")
    print(f"Header row:    {provenance.header_row_index}")
    print(f"Events loaded: {len(result.normalized_data)}")
    print(f"Warnings:      {len(provenance.warnings)}")
    print(f"Mapped cols:   {len(provenance.column_map)}")
    print()
    print("Identifiers, warning text, and event values are never printed.")
    print()


def main(
    file_path: str | None = None,
    settings: str | dict | PyskindoseSettings | None = None,
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
    return None

def analyze_input_file(
    file_path: str | Path,
    settings: str | dict | PyskindoseSettings | None = None,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
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
        Schema adapter for tabular files ("normalized", "generic_rdsr_like",
        "radimetrics", "dosetrack", or "auto" to detect from column headers).
        ``None`` uses the library default ("normalized"); the CLI defaults to
        "auto".
    sheet_name:
        Sheet name or 0-based index for Excel files (ignored otherwise).
    output_format:
        "dict" (default), "json", or "html".
    """
    settings_obj = _settings_with_output_format(settings, output_format)
    input_result = _read_input_for_analysis(file_path, settings_obj, input_schema, sheet_name)
    if Path(file_path).suffix.lower() in _TABULAR_SUFFIXES:
        _warn_for_tabular_input(input_result)
    return _analysis_output_for_input(input_result, settings_obj, output_format)


def analyze_multiple_input_files(
    file_paths: Sequence[str | Path],
    settings: str | dict | PyskindoseSettings | None = None,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
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
    from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance
    from guiskindose.input_adapters.registry import read_and_normalize_input

    settings_obj = parse_settings_to_settings_class(settings=settings)
    
    if settings_obj.output_format == "html":
        logger.warning("HTML output format is not supported for multi-exam runs. Forcing to dict.")
        settings_obj.output_format = "dict"
    
    all_exams: list[InputAdapterResult] = []

    resolved_paths: list[Path] = []
    for fp in file_paths:
        p = Path(fp)
        if not p.exists() and ("*" in str(p) or "?" in str(p)):
            resolved_paths.extend(sorted(p.parent.glob(p.name)))
        else:
            resolved_paths.append(p)

    for fp in resolved_paths:
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
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    include_sensitive_values: bool = False,
) -> None:
    """Print a value-safe preview unless sensitive values are explicitly requested."""
    from guiskindose.input_adapters.registry import read_and_normalize_input

    # The radimetrics/generic/dosetrack schemas need settings (rdsr_normalizer
    # does a manufacturer/model lookup), so supply defaults — preview never runs
    # a dose calculation, so example settings are sufficient.
    settings_obj = parse_settings_to_settings_class(settings=None)

    raw = read_and_normalize_input(
        file_path,
        input_schema=input_schema,
        sheet_name=sheet_name,
        settings=settings_obj,
    )
    results = raw if isinstance(raw, list) else [raw]
    for index, result in enumerate(results):
        _print_input_preview(result, index, include_sensitive_values)


def analyze_normalized_data_with_custom_settings_object(
    data_norm: pd.DataFrame,
    settings: PyskindoseSettings | str | dict,
    output_format: str | None = RUN_ARGUMENTS_OUTPUT_JSON,
) -> str | dict[str, Any] | PySkinDoseOutput:
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


class _WarningCapture(logging.Handler):
    """Collect WARNING+ records from the ``guiskindose`` logger for export.

    Used only during headless export so calculation-level QA warnings are
    preserved on the payload without changing the JSON export schema.
    """

    def __init__(self) -> None:
        """Create a WARNING-level handler that stores messages in-memory."""
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Append the formatted log message to the capture list."""
        self.messages.append(record.getMessage())


def build_cli_export_source(
    file_paths: Sequence[str | Path],
    settings: str | dict | PyskindoseSettings | None,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    report_title: str | None = None,
    include_source_identifiers: bool = False,
):
    """Run a calculation for export and assemble an ``ExportSource`` (no GUI).

    Handles single RDSR / tabular files and multi-file (multi-exam) runs, forcing
    ``output_format='dict'`` and capturing calculation warnings.
    """
    from guiskindose.export import build_export_source_from_cli
    from guiskindose.input_adapters.registry import read_and_normalize_input

    settings_obj = parse_settings_to_settings_class(settings=settings)
    # Force a dose calculation with structured output regardless of the settings
    # file's mode/format (which may be a plot mode).
    settings_obj.mode = "calculate_dose"
    settings_obj.output_format = "dict"

    capture = _WarningCapture()
    pkg_logger = logging.getLogger("guiskindose")
    pkg_logger.addHandler(capture)
    try:
        resolved: list[Path] = []
        for fp in file_paths:
            p = Path(fp)
            if not p.exists() and ("*" in str(p) or "?" in str(p)):
                resolved.extend(sorted(p.parent.glob(p.name)))
            else:
                resolved.append(p)

        single_tabular_multi = False
        if len(resolved) == 1 and resolved[0].suffix.lower() in _TABULAR_SUFFIXES:
            probe = read_and_normalize_input(
                resolved[0], input_schema=input_schema, sheet_name=sheet_name, settings=settings_obj
            )
            single_tabular_multi = isinstance(probe, list)

        if len(resolved) > 1 or single_tabular_multi:
            inputs = _load_inputs_for_export(resolved, settings_obj, input_schema, sheet_name)
            result = analyze_multiple_exams(inputs, settings_obj)
            source = build_export_source_from_cli(
                settings_obj,
                multi_exam_result=result,
                inputs=inputs,
                calc_warnings=list(capture.messages),
                import_warnings=[w for e in inputs for w in e.warnings],
                file_name=str(resolved[0]) if resolved else None,
                report_title=report_title,
                include_source_identifiers=include_source_identifiers,
            )
            return source

        # Single-exam path.
        single = resolved[0]
        if single.suffix.lower() in _TABULAR_SUFFIXES:
            adapter = read_and_normalize_input(
                single, input_schema=input_schema, sheet_name=sheet_name, settings=settings_obj
            )
            assert not isinstance(adapter, list)  # ruled out above
            data_norm = adapter.normalized_data
            inputs = [adapter]
            import_warnings = list(adapter.warnings)
        else:
            data_norm = read_and_normalise_rdsr_data(rdsr_filepath=str(single), settings=settings_obj)
            inputs = None
            import_warnings = []

        output = analyze_data(normalized_data=data_norm, settings=settings_obj)
        return build_export_source_from_cli(
            settings_obj,
            output_dict=output if isinstance(output, dict) else None,
            inputs=inputs,
            single_normalized_data=data_norm,
            single_source_file=single.name,
            calc_warnings=list(capture.messages),
            import_warnings=import_warnings,
            file_name=single.name,
            report_title=report_title,
            include_source_identifiers=include_source_identifiers,
        )
    finally:
        pkg_logger.removeHandler(capture)


def _load_inputs_for_export(resolved_paths, settings_obj, input_schema, sheet_name):
    """Load one ``InputAdapterResult`` per exam (parallel to multi-exam output)."""
    from guiskindose.input_adapters.models import InputAdapterResult, InputProvenance
    from guiskindose.input_adapters.registry import read_and_normalize_input

    inputs: list = []
    for fp in resolved_paths:
        fp = Path(fp)
        suffix = fp.suffix.lower()
        if suffix in _TABULAR_SUFFIXES:
            result = read_and_normalize_input(
                fp, input_schema=input_schema, sheet_name=sheet_name, settings=settings_obj
            )
            inputs.extend(result if isinstance(result, list) else [result])
        else:
            data_norm = read_and_normalise_rdsr_data(rdsr_filepath=str(fp), settings=settings_obj)
            inputs.append(
                InputAdapterResult(
                    normalized_data=data_norm,
                    raw_data=None,
                    provenance=InputProvenance(
                        source_type=suffix.lstrip("."), schema_name="rdsr", original_filename=fp.name,
                        header_row_index=0, detected_encoding="n/a", detected_delimiter=None,
                        sheet_name=None, column_map={}, unit_conversions={}, warnings=[],
                    ),
                    warnings=[],
                )
            )
    return inputs


def validate_export_flags(
    export_format: str | None,
    *,
    aggregate_only: bool,
    input_preview_only: bool,
    has_files: bool,
) -> None:
    """Reject incompatible ``--export-format`` flag combinations (plan §5.2.4).

    Raises ``ValueError`` with a user-facing message; callers translate to
    ``SystemExit``.
    """
    if not export_format:
        return
    if aggregate_only:
        raise ValueError("--export-format cannot be combined with --aggregate.")
    if input_preview_only:
        raise ValueError("--export-format cannot be combined with --input-preview-only.")
    if not has_files:
        raise ValueError("--export-format requires at least one --file-path.")


def run_cli_export(
    file_paths: Sequence[str | Path],
    settings: str | dict | PyskindoseSettings | None,
    export_format: str,
    *,
    export_path: Path | None = None,
    export_title: str | None = None,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    include_source_identifiers: bool = False,
    force: bool = False,
    allow_ignored_checkout: bool = False,
) -> Path:
    """Build a Rich report from a headless run and write it to disk. Returns the path."""
    from guiskindose.export import collect_export_payload
    from guiskindose.export.writers import write_report
    from guiskindose.safe_output import validate_output_path

    if export_path is None:
        raise ValueError("--export-path is required for filesystem report exports.")

    # Fail fast on an invalid/forbidden/existing destination before the expensive
    # dose calculation and report render. write_report re-validates atomically.
    validate_output_path(export_path, force=force, allow_ignored_checkout=allow_ignored_checkout)

    source = build_cli_export_source(
        file_paths,
        settings,
        input_schema=input_schema,
        sheet_name=sheet_name,
        report_title=export_title,
        include_source_identifiers=include_source_identifiers,
    )
    payload = collect_export_payload(source)
    write_report(payload, export_path, export_format, force=force, allow_ignored_checkout=allow_ignored_checkout)
    return Path(export_path)


def get_argument_parser(arguments) -> "argparse.Namespace":
    """Parse CLI argv into an argparse Namespace for guiskindose.

    Thin re-export of :func:`guiskindose.cli_args.get_argument_parser` (Phase 4c
    extracted the parser construction to a dedicated module so this file stays
    under the repo's 800-line ceiling).
    """
    return _cli_args_get_argument_parser(arguments)


if __name__ == "__main__":
    install_value_safe_excepthook(logger)
    args = get_argument_parser(sys.argv[1:])

    if args.mode == RUN_ARGUMENTS_MODE_GUI:
        from guiskindose.gui.app import run_gui
        run_gui(
            native=getattr(args, "native", False),
            host=getattr(args, "host", None),
            allow_network=getattr(args, "allow_network", False),
        )
    else:
        if (run_settings := args.settings) is None:
            logger.warning("No settings specified. Running with development parameters")
            run_settings = DEVELOPMENT_PARAMETERS

        # Apply kerma-meter CLI overrides onto a concrete settings object once.
        settings_for_run = parse_settings_to_settings_class(settings=run_settings)
        apply_kerma_meter_cli_flags(settings_for_run, args)
        run_settings = settings_for_run

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
            except ValueError as exc:
                raise SystemExit(safe_user_error("invalid_export_options")) from exc
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
            suffix = Path(single_path).suffix.lower()
            if suffix in _TABULAR_SUFFIXES:
                if getattr(args, "input_preview_only", False):
                    preview_input_file(
                        single_path,
                        input_schema=getattr(args, "input_schema", None),
                        sheet_name=getattr(args, "sheet_name", 0),
                        include_sensitive_values=getattr(args, "include_sensitive_preview", False),
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
