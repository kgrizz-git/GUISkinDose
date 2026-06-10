"""Stub adapter for DoseWatch dose-management exports (not yet implemented).

To implement this adapter:
1. Obtain a real DoseWatch export (CSV or XLSX).
2. Document its column headers and units below, then populate
   DOSEWATCH_COLUMN_NAMES and DOSEWATCH_PATTERNS (see column_mapper.py for examples).
3. Replace the adapt() body with the actual transform logic.
4. Add DOSEWATCH_COLUMN_NAMES to registry._SCHEMA_KNOWN_NAMES for auto-detection.
5. Add a fixture to tests/fixtures/tabular_inputs/ and write tests.
"""

from __future__ import annotations

from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings

# TODO: populate once a real DoseWatch export is available.
# Lowercase versions of key DoseWatch column headers (for detect_header_row scoring).
DOSEWATCH_COLUMN_NAMES: frozenset[str] = frozenset()

# TODO: populate once a real DoseWatch export is available.
# Maps internal rdsr_parser column names → list of lowercase DoseWatch header patterns.
DOSEWATCH_PATTERNS: dict[str, list[str]] = {}


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Not yet implemented — requires a real DoseWatch export for column mapping.

    Raises NotImplementedError unconditionally until DOSEWATCH_COLUMN_NAMES and
    DOSEWATCH_PATTERNS are populated and the transform logic is written.
    """
    raise NotImplementedError(
        "The DoseWatch adapter is not yet implemented. "
        "No real DoseWatch export is available for column-map research. "
        "To implement: populate DOSEWATCH_COLUMN_NAMES and DOSEWATCH_PATTERNS in "
        "src/mypyskindose/input_adapters/dosewatch.py, then add the transform logic. "
        "See src/mypyskindose/input_adapters/dosetrack.py for a reference implementation."
    )
