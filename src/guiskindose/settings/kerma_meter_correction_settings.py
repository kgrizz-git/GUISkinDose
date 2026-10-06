"""Settings for kerma-meter correction factors (per equipment × tube)."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Legacy ``mode`` values, kept only so old settings files and CLI calls still load.
_LEGACY_MODES = frozenset({"file", "prompt"})
_CF_SUSPICIOUS_LO = 0.5
_CF_SUSPICIOUS_HI = 2.0


class KermaMeterCorrectionSettings:
    """User-supplied kerma-meter CF configuration.

    Attributes
    ----------
    enable : bool
        When False, CF is skipped (all factors 1.0) and no file I/O occurs.
    file : Path | None
        Path to a CSV/TSV/XLSX/JSON correction table. When set, it always loads.
        Resolution order per ``(equipment, tube)``: ``in_memory_table`` (manual
        entry), then ``file`` rows, then ``default_factor``.
    file_sheet : str | int | None
        Optional Excel sheet name/index.
    default_factor : float
        Fail-soft CF when identity is unresolved or the table misses a key.
    explicit_label : str | None
        Force every event to this equipment label (overrides serial/station).
    prompt_at_calc : bool
        GUI-only: open the CF prompt before calculation. Non-GUI runs never
        prompt and use the file and ``default_factor``.
    in_memory_table : dict[tuple[str, str], float] | None
        Session override (GUI prompt / tests); wins over file keys when both set.

    unresolved_equipment_labels : dict[str, str]
        Runtime-only per-exam identity overrides keyed by opaque exam label
        (``"Exam 1"``). Used for events with no serial/station so they reach the
        table. Never serialized by ``to_dict()`` (labels are site identifiers).

    Notes
    -----
    The exclusive ``mode`` setting (``"file"`` / ``"prompt"``) is deprecated and
    no longer stored. A ``mode`` key in the input dict is still accepted: it logs
    a deprecation warning, ``"prompt"`` maps to ``prompt_at_calc=True``, and
    ``"file"`` is a no-op. ``to_dict()`` never emits ``mode``.
    """

    def __init__(self, raw: dict[str, Any] | None = None):
        """Parse a settings dict into kerma-meter CF fields with validation."""
        data = raw or {}
        self.enable: bool = bool(data.get("enable", False))
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
        legacy_mode = data.get("mode")
        if legacy_mode is not None:
            self.apply_legacy_mode(legacy_mode)
        # Runtime-only (not serialized to example JSON).
        self.in_memory_table: dict[tuple[str, str], float] | None = data.get("in_memory_table")
        self.unresolved_equipment_labels: dict[str, str] = dict(data.get("unresolved_equipment_labels") or {})

    def apply_legacy_mode(self, mode: object) -> None:
        """Map the deprecated exclusive ``mode`` onto the unified source model.

        Parameters
        ----------
        mode : object
            ``"file"`` (no-op: a set file always loads) or ``"prompt"`` (sets
            ``prompt_at_calc``). Case and surrounding whitespace are ignored.

        Raises
        ------
        ValueError
            If *mode* is not ``"file"`` or ``"prompt"``.
        """
        text = str(mode).strip().lower()
        if text not in _LEGACY_MODES:
            raise ValueError(f"kerma_meter_correction.mode must be one of {sorted(_LEGACY_MODES)}")
        logger.warning(
            "kerma_meter_correction.mode is deprecated and ignored as an exclusive switch; "
            "a correction file always loads and manual entries win over it. "
            "Use prompt_at_calc to ask before calculation."
        )
        if text == "prompt":
            self.prompt_at_calc = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize settings for export / round-trip (excludes in_memory_table)."""
        return {
            "enable": self.enable,
            "file": str(self.file) if self.file is not None else None,
            "file_sheet": self.file_sheet,
            "default_factor": self.default_factor,
            "explicit_label": self.explicit_label,
            "prompt_at_calc": self.prompt_at_calc,
        }
