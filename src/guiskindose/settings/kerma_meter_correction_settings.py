"""Settings for kerma-meter correction factors (per equipment × tube)."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_VALID_MODES = frozenset({"file", "prompt"})
_CF_SUSPICIOUS_LO = 0.5
_CF_SUSPICIOUS_HI = 2.0


class KermaMeterCorrectionSettings:
    """User-supplied kerma-meter CF configuration.

    Attributes
    ----------
    enable : bool
        When False, CF is skipped (all factors 1.0) and no file I/O occurs.
    mode : str
        ``"file"`` or ``"prompt"``. Prompt is GUI-only; CLI/non-GUI falls soft
        to ``default_factor``.
    file : Path | None
        Path to a CSV/TSV/XLSX/JSON correction table.
    file_sheet : str | int | None
        Optional Excel sheet name/index.
    default_factor : float
        Fail-soft CF when identity is unresolved or the table misses a key.
    explicit_label : str | None
        Force every event to this equipment label (overrides serial/station).
    prompt_at_calc : bool
        GUI-only: open the CF prompt before calculation.
    in_memory_table : dict[tuple[str, str], float] | None
        Session override (GUI prompt / tests); wins over file keys when both set.
    """

    def __init__(self, raw: dict[str, Any] | None = None):
        """Parse a settings dict into kerma-meter CF fields with validation."""
        data = raw or {}
        self.enable: bool = bool(data.get("enable", False))
        mode = str(data.get("mode", "file")).strip().lower()
        if mode not in _VALID_MODES:
            raise ValueError(f"kerma_meter_correction.mode must be one of {sorted(_VALID_MODES)}")
        self.mode: str = mode

        file_raw = data.get("file")
        if file_raw is None or file_raw == "":
            self.file: Path | None = None
        else:
            self.file = Path(str(file_raw))

        sheet = data.get("file_sheet")
        if sheet is None or sheet == "":
            self.file_sheet: str | int | None = None
        else:
            self.file_sheet = sheet

        self.default_factor: float = float(data.get("default_factor", 1.0))
        if not math.isfinite(self.default_factor) or self.default_factor <= 0:
            raise ValueError("kerma_meter_correction.default_factor must be a finite float > 0")
        if not (_CF_SUSPICIOUS_LO <= self.default_factor <= _CF_SUSPICIOUS_HI):
            logger.warning(
                "kerma_meter_correction.default_factor=%.4g is outside [%.1f, %.1f]",
                self.default_factor,
                _CF_SUSPICIOUS_LO,
                _CF_SUSPICIOUS_HI,
            )

        label = data.get("explicit_label")
        self.explicit_label: str | None = None if label in (None, "") else str(label)
        self.prompt_at_calc: bool = bool(data.get("prompt_at_calc", False))
        # Runtime-only (not serialized to example JSON).
        self.in_memory_table: dict[tuple[str, str], float] | None = data.get("in_memory_table")

    def to_dict(self) -> dict[str, Any]:
        """Serialize settings for export / round-trip (excludes in_memory_table)."""
        return {
            "enable": self.enable,
            "mode": self.mode,
            "file": str(self.file) if self.file is not None else None,
            "file_sheet": self.file_sheet,
            "default_factor": self.default_factor,
            "explicit_label": self.explicit_label,
            "prompt_at_calc": self.prompt_at_calc,
        }
