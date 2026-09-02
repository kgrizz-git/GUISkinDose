"""Placeholder adapters for vendor exports with no implementation yet.

Qaelum, DoseMonitor, and DoseWatch are wired into the registry for explicit
``--input-schema`` selection so the error message names a real schema, but each
raises ``NotImplementedError`` with implementation instructions until a real
export is available to build its column map. They are deliberately excluded from
auto-detection (``registry._SCHEMA_KNOWN_NAMES``).

To implement one:
1. Obtain a real export (CSV or XLSX) from the vendor's dose-management tool.
2. Add ``<VENDOR>_COLUMN_NAMES`` and ``<VENDOR>_PATTERNS`` to ``column_mapper.py``.
3. Create a real adapter module following ``radimetrics.py``/``dosetrack.py``
   (a thin ``adapt()`` over ``base.run_normalizer_pipeline`` with a transform).
4. Register it in ``registry.py`` and add it to ``_SCHEMA_KNOWN_NAMES``.
5. Add a fixture to ``tests/fixtures/tabular_inputs/`` and write tests.
"""

from __future__ import annotations

from typing import NoReturn

# schema name → human-readable vendor label.
STUB_VENDORS: dict[str, str] = {
    "qaelum": "Qaelum",
    "dosemonitor": "DoseMonitor",
    "dosewatch": "DoseWatch",
}


def raise_not_implemented(schema: str) -> NoReturn:
    """Raise NotImplementedError for a stub vendor schema with how-to guidance."""
    label = STUB_VENDORS.get(schema, schema)
    raise NotImplementedError(
        f"The {label} adapter is not yet implemented. "
        f"No real {label} export is available for column-map research. "
        f"To implement: add {schema.upper()}_COLUMN_NAMES and {schema.upper()}_PATTERNS to "
        "column_mapper.py and create an adapter module following dosetrack.py. "
        "See src/guiskindose/input_adapters/stubs.py for the full checklist."
    )
