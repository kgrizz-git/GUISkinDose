"""Route tabular input files to the correct schema adapter."""

from __future__ import annotations

from pathlib import Path

from mypyskindose.input_adapters import normalized as normalized_adapter
from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.tabular_loader import load

_TABULAR_SUFFIXES = frozenset({".csv", ".tsv", ".xlsx", ".xlsm"})

_SUPPORTED_SCHEMAS = ("normalized",)
# Phase 2+: "generic_rdsr_like", "radimetrics", "dosetrack"


def read_and_normalize_input(
    file_path: str | Path,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
) -> InputAdapterResult:
    """Load a tabular file and return a normalized InputAdapterResult.

    Parameters
    ----------
    file_path:
        Path to a .csv, .tsv, .xlsx, or .xlsm file.
    input_schema:
        Which schema adapter to use. Currently only "normalized" is supported
        (Phase 1). Pass None to use the default for the file type ("normalized").
        "auto" will be wired once ≥2 schemas are available (Phase 3+).
    sheet_name:
        Sheet name or 0-based index for Excel files (ignored for CSV/TSV).

    Raises
    ------
    ValueError
        On unsupported suffix, unsupported schema, or data validation failures.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in _TABULAR_SUFFIXES:
        raise ValueError(
            f"Unsupported suffix {suffix!r}. "
            "The tabular adapter handles .csv, .tsv, .xlsx, .xlsm. "
            "For DICOM RDSR or JSON use read_and_normalise_rdsr_data()."
        )

    schema = input_schema or "normalized"

    if schema == "auto":
        raise ValueError(
            "'auto' schema detection is not yet supported (Phase 3+). "
            f"Pass one of {_SUPPORTED_SCHEMAS!r} explicitly."
        )

    if schema not in _SUPPORTED_SCHEMAS:
        raise ValueError(
            f"Unknown schema {schema!r}. Supported: {_SUPPORTED_SCHEMAS!r}. "
            "Additional vendor schemas (generic_rdsr_like, radimetrics, dosetrack) "
            "will be added in later phases."
        )

    loaded = load(path, sheet_name=sheet_name)
    result = normalized_adapter.adapt(loaded, original_filename=path.name)

    # Propagate sheet_name into provenance for Excel files
    if suffix in (".xlsx", ".xlsm"):
        result.provenance.sheet_name = sheet_name

    return result
