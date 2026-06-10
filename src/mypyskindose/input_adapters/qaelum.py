"""Stub adapter for Qaelum dose-management exports (not yet implemented).

To implement this adapter:
1. Obtain a real Qaelum export (CSV or XLSX).
2. Document its column headers and units below, then populate
   QAELUM_COLUMN_NAMES and QAELUM_PATTERNS (see column_mapper.py for examples).
3. Replace the adapt() body with the actual transform logic.
4. Add QAELUM_COLUMN_NAMES to registry._SCHEMA_KNOWN_NAMES for auto-detection.
5. Add a fixture to tests/fixtures/tabular_inputs/ and write tests.
"""

from __future__ import annotations

from mypyskindose.input_adapters.models import InputAdapterResult
from mypyskindose.input_adapters.tabular_loader import _RawLoad
from mypyskindose.settings import PyskindoseSettings

# TODO: populate once a real Qaelum export is available.
# Lowercase versions of key Qaelum column headers (for detect_header_row scoring).
QAELUM_COLUMN_NAMES: frozenset[str] = frozenset()

# TODO: populate once a real Qaelum export is available.
# Maps internal rdsr_parser column names → list of lowercase Qaelum header patterns.
QAELUM_PATTERNS: dict[str, list[str]] = {}


def adapt(
    loaded: _RawLoad,
    original_filename: str,
    settings: PyskindoseSettings,
) -> InputAdapterResult:
    """Not yet implemented — requires a real Qaelum export for column mapping.

    Raises NotImplementedError unconditionally until QAELUM_COLUMN_NAMES and
    QAELUM_PATTERNS are populated and the transform logic is written.
    """
    raise NotImplementedError(
        "The Qaelum adapter is not yet implemented. "
        "No real Qaelum export is available for column-map research. "
        "To implement: populate QAELUM_COLUMN_NAMES and QAELUM_PATTERNS in "
        "src/mypyskindose/input_adapters/qaelum.py, then add the transform logic. "
        "See src/mypyskindose/input_adapters/dosetrack.py for a reference implementation."
    )
