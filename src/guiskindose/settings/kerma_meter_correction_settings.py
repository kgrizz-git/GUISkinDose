"""Settings for kerma-meter correction factors (per equipment × tube)."""

from __future__ import annotations

import logging
import math
from datetime import date
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
        Resolution order per exam and ``(equipment, tube)``: ``in_memory_table``
        (manual entry for that exam), then the ``file`` row for the exam's
        calibration period, then ``default_factor``. The file may carry optional
        ``valid_from`` / ``valid_to`` ISO-date columns.
    file_sheet : str | int | None
        Optional Excel sheet name/index.
    default_factor : float
        Fail-soft CF when identity is unresolved or the table misses a key.
    explicit_label : str | None
        Force every event to this equipment label (overrides serial/station).
    ask_for_missing : bool
        GUI-only, default ``True``: open the CF dialog when a detected
        ``(equipment, tube)`` pair has no factor (manual entry or file row).
        Non-GUI runs never prompt and use the file and ``default_factor``.
        Replaces the old ``prompt_at_calc`` flag, which is still accepted on
        input (see Notes).
    calibration_periods : dict[str, str]
        Runtime-only calibration-period choice per exam (opaque exam label ->
        period key ``"<valid_from>|<valid_to>"``). Selects which dated file rows
        apply to that exam. Never serialized.
    calibration_date : datetime.date | None
        Runtime-only date chosen by ``--kerma-meter-calibration-date``: the period
        containing it applies to every exam without a ``calibration_periods`` entry.
        Never serialized.
    in_memory_table : dict[tuple[str, ...], float] | None
        Session override (GUI dialog / tests); wins over file rows. Keys are
        ``(exam label, equipment, tube)`` for per-exam entries; a legacy
        ``(equipment, tube)`` key applies to every exam.
    unresolved_equipment_labels : dict[str, str]
        Runtime-only per-exam identity overrides keyed by opaque exam label
        (``"Exam 1"``). Used for events with no serial/station so they reach the
        table. Never serialized by ``to_dict()`` (labels are site identifiers).
    periods_acknowledged : set[str]
        Runtime-only opaque exam labels whose default calibration period the user
        accepted in the GUI dialog. Those exams skip the unselected-period warning.
        Never serialized.

    Notes
    -----
    The exclusive ``mode`` setting (``"file"`` / ``"prompt"``) is deprecated and
    no longer stored. A ``mode`` key in the input dict is still accepted: it logs
    a deprecation warning, ``"prompt"`` maps to ``ask_for_missing=True``, and
    ``"file"`` is a no-op. A legacy ``prompt_at_calc`` of ``True`` also maps to
    ``ask_for_missing=True``; ``False`` was only the old default and is ignored.
    Legacy keys never override an explicit ``ask_for_missing``. ``to_dict()``
    emits neither ``mode`` nor ``prompt_at_calc``.
    """

    def __init__(self, raw: dict[str, Any] | None = None):
        """Parse a settings dict into kerma-meter CF fields with validation."""
        data = raw or {}
        self.enable: bool = bool(data.get("enable", False))
        file_raw = data.get("file")
        self.file: Path | None = None if file_raw in (None, "") else Path(str(file_raw))
        sheet = data.get("file_sheet")
        self.file_sheet: str | int | None = None if sheet in (None, "") else sheet

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
        self.ask_for_missing: bool = bool(data.get("ask_for_missing", True))
        # True when the input stated ask_for_missing itself; legacy keys then never override it.
        self.ask_for_missing_explicit: bool = "ask_for_missing" in data
        if data.get("prompt_at_calc") and "ask_for_missing" not in data:
            self.ask_for_missing = True
        legacy_mode = data.get("mode")
        if legacy_mode is not None:
            self.apply_legacy_mode(legacy_mode)
        # Runtime-only (not serialized to example JSON).
        self.in_memory_table: dict[tuple[str, ...], float] | None = data.get("in_memory_table")
        # Runtime-only calibration-period choice: per exam (GUI) or one date (CLI).
        self.calibration_periods: dict[str, str] = dict(data.get("calibration_periods") or {})
        self.calibration_date: date | None = self._parse_calibration_date(data.get("calibration_date"))
        self.unresolved_equipment_labels: dict[str, str] = dict(data.get("unresolved_equipment_labels") or {})
        # Runtime-only: exams whose default (current) calibration period the user accepted in the GUI.
        self.periods_acknowledged: set[str] = set(data.get("periods_acknowledged") or ())

    @staticmethod
    def _parse_calibration_date(value: object) -> date | None:
        """Coerce ``None`` / a date / an ISO ``YYYY-MM-DD`` string to a date.

        Raises
        ------
        ValueError
            If the value is anything else, including a malformed date string.
        """
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip())
            except ValueError as exc:
                raise ValueError("kerma_meter_correction.calibration_date must be an ISO date (YYYY-MM-DD)") from exc
        raise ValueError("kerma_meter_correction.calibration_date must be a date or an ISO date string")

    def apply_legacy_mode(self, mode: object, *, explicit: bool | None = None) -> None:
        """Map the deprecated exclusive ``mode`` onto the unified source model.

        Parameters
        ----------
        mode : object
            ``"file"`` (no-op: a set file always loads) or ``"prompt"`` (sets
            ``ask_for_missing``). Case and surrounding whitespace are ignored.
        explicit : bool | None
            True when ``ask_for_missing`` was given explicitly; it then wins.
            ``None`` (default) uses ``ask_for_missing_explicit`` recorded at
            construction, so a later CLI flag cannot override an explicit
            ``ask_for_missing=False`` from the settings file.

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
            "Use ask_for_missing to control the missing-factor dialog."
        )
        if explicit is None:
            explicit = self.ask_for_missing_explicit
        if text == "prompt" and not explicit:
            self.ask_for_missing = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize settings for export / round-trip (excludes in_memory_table)."""
        return {
            "enable": self.enable,
            "file": str(self.file) if self.file is not None else None,
            "file_sheet": self.file_sheet,
            "default_factor": self.default_factor,
            "explicit_label": self.explicit_label,
            "ask_for_missing": self.ask_for_missing,
        }
