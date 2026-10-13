"""Per-exam equipment identity contract (Phase 1, custom equipment profiles).

Coordinate identity is canonical manufacturer/model for one homogeneous exam
(SPEC §5, decision 2): one frame carries exactly one canonical
``(manufacturer, model)`` pair. This module is the single
validation/classification seam for that identity:

- :func:`clean_identity_value` maps blank/None/NaN/``"nan"`` text to ``None``
  without ever stringifying missing values into matchable ``"none"``/``"nan"``.
- :func:`frame_identities` lists the distinct raw ``(manufacturer, model)``
  pairs of a frame in first-appearance order, spellings preserved.
- :func:`canonical_identity_pairs` lists the distinct canonical pairs, both
  axes through the existing key normalizers (no vendor aliases): key spelling
  variants are one pair, blanks map to ``None``.
- :func:`classify_exam_identity` describes one exam frame as homogeneous,
  missing-manufacturer, model-variation, or mixed-manufacturer. The
  classification is descriptive only.
- :func:`require_homogeneous_identity` is the guard: it fails closed
  (value-free :class:`RdsrInputError`) on anything but one canonical pair.
  Same-maker model variation, distinct canonical makers, and known+unknown
  mixes are all rejected — no row silently borrows another row's identity, and
  the established row-0 selection only ever runs on a proven-homogeneous
  frame. Only an all-unknown frame stays compatible (legacy model-only path).
  Nothing here infers a maker from a profile model/alias set.

This is not profile activation or matching: no custom coordinates are applied,
no store is read, and coordinates/dose are untouched. Callers split mixed
frames at their established per-exam boundary (study-id groups) or reject.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from guiskindose.constants import KEY_NORMALIZATION_MANUFACTURER, KEY_NORMALIZATION_MODEL_NAME
from guiskindose.privacy import opaque_exam_label
from guiskindose.rdsr_input_checks import RdsrInputError
from guiskindose.settings.normalization_settings import normalize_manufacturer_key, normalize_model_key

__all__ = [
    "HOMOGENEOUS",
    "MISSING_MANUFACTURER",
    "MIXED_MANUFACTURER",
    "MODEL_VARIATION",
    "canonical_identity_pairs",
    "classify_exam_identity",
    "clean_identity_value",
    "frame_identities",
    "require_homogeneous_identity",
]

#: :func:`classify_exam_identity` outcomes, descriptive only — the guard
#: (:func:`require_homogeneous_identity`) rejects everything but a single
#: canonical pair, whatever the label. ``HOMOGENEOUS`` is one canonical pair
#: with a present maker; ``MISSING_MANUFACTURER`` is one canonical pair with
#: no maker (legacy all-unknown compatibility); ``MODEL_VARIATION`` is several
#: pairs under one canonical maker; ``MIXED_MANUFACTURER`` is several
#: canonical makers.
HOMOGENEOUS = "homogeneous"
MISSING_MANUFACTURER = "missing_manufacturer"
MODEL_VARIATION = "model_variation"
MIXED_MANUFACTURER = "mixed_manufacturer"

#: Raw texts that are missing-value artifacts, never a real maker or model.
_BLANK_TEXTS = frozenset({"", "nan", "nat", "none"})


def clean_identity_value(value: object) -> str | None:
    """Return the stripped identity text, or ``None`` when it carries no identity.

    ``None``, NaN/NaT, blank strings, and case-insensitive ``"nan"``/``"nat"``/
    ``"none"`` artifacts all map to ``None`` so a missing maker or model can
    never stringify into a matchable ``"none"``/``"nan"`` key. Any other value
    keeps its exact spelling (no case folding); matching normalizes later.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        return None if not text or text.casefold() in _BLANK_TEXTS else text
    candidate: Any = value
    try:
        if bool(pd.isna(candidate)):
            return None
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if not text or text.casefold() in _BLANK_TEXTS:
        return None
    return text


def _identity_columns(frame: pd.DataFrame) -> tuple[str, str]:
    """Return the (manufacturer, model) column names for a raw or normalized frame."""
    manufacturer_col = (
        KEY_NORMALIZATION_MANUFACTURER if KEY_NORMALIZATION_MANUFACTURER in frame.columns else "Manufacturer"
    )
    model_col = (
        KEY_NORMALIZATION_MODEL_NAME if KEY_NORMALIZATION_MODEL_NAME in frame.columns else "ManufacturerModelName"
    )
    return manufacturer_col, model_col


def frame_identities(frame: pd.DataFrame) -> tuple[tuple[str | None, str | None], ...]:
    """Distinct raw ``(manufacturer, model)`` pairs in first-appearance order.

    Values are cleaned (:func:`clean_identity_value`) but otherwise verbatim —
    no normalization, no inference. An empty frame yields ``()``. A seen-set
    keeps this linear in the row count.
    """
    if frame.empty:
        return ()
    manufacturer_col, model_col = _identity_columns(frame)
    manufacturers = (
        frame[manufacturer_col].tolist() if manufacturer_col in frame.columns else [None] * len(frame)
    )
    models = frame[model_col].tolist() if model_col in frame.columns else [None] * len(frame)
    seen: set[tuple[str | None, str | None]] = set()
    pairs: list[tuple[str | None, str | None]] = []
    for raw_maker, raw_model in zip(manufacturers, models, strict=True):
        pair = (clean_identity_value(raw_maker), clean_identity_value(raw_model))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    return tuple(pairs)


def _canonical_pair(pair: tuple[str | None, str | None]) -> tuple[str | None, str | None]:
    """Canonicalize one raw pair on both axes; blanks become ``None``."""
    maker, model = pair
    maker_key = normalize_manufacturer_key(maker) if maker is not None else ""
    model_key = normalize_model_key(model) if model is not None else ""
    return (maker_key or None, model_key or None)


def canonical_identity_pairs(frame: pd.DataFrame) -> tuple[tuple[str | None, str | None], ...]:
    """Distinct canonical ``(manufacturer, model)`` pairs in first-appearance order.

    Both axes run through the existing key normalizers (no vendor aliases), so
    key spelling variants (case, punctuation, spacing) collapse to one pair
    while distinct canonical keys stay distinct — including alias-family
    spellings such as ``"Siemens"`` vs ``"Siemens Healthcare"``.
    """
    seen: set[tuple[str | None, str | None]] = set()
    pairs: list[tuple[str | None, str | None]] = []
    for pair in frame_identities(frame):
        canonical = _canonical_pair(pair)
        if canonical not in seen:
            seen.add(canonical)
            pairs.append(canonical)
    return tuple(pairs)


def missing_maker_rows(frame: pd.DataFrame) -> int:
    """Count of rows in *frame* whose maker identity is missing (blank/None/NaN)."""
    if frame.empty:
        return 0
    manufacturer_col, _ = _identity_columns(frame)
    if manufacturer_col not in frame.columns:
        return len(frame)
    return sum(1 for value in frame[manufacturer_col].tolist() if clean_identity_value(value) is None)


def classify_exam_identity(frame: pd.DataFrame) -> str:
    """Describe one exam frame's equipment identity (one of the module constants).

    Descriptive only: the guard rejects everything but a single canonical
    pair. One canonical pair with a present maker is ``HOMOGENEOUS``; one
    canonical pair with no maker is ``MISSING_MANUFACTURER`` (legacy
    all-unknown compatibility); several pairs under one canonical maker are
    ``MODEL_VARIATION``; several canonical makers are ``MIXED_MANUFACTURER``.
    """
    pairs = canonical_identity_pairs(frame)
    if not pairs:
        return MISSING_MANUFACTURER
    makers = {maker for maker, _ in pairs if maker is not None}
    if len(makers) > 1:
        return MIXED_MANUFACTURER
    if len(pairs) > 1:
        return MODEL_VARIATION
    first_maker = next(iter(pairs))[0]
    if first_maker is None:
        return MISSING_MANUFACTURER
    return HOMOGENEOUS


def require_homogeneous_identity(frame: pd.DataFrame, *, exam_index: int | None = None) -> None:
    """Fail closed unless one frame carries exactly one canonical identity pair.

    Raises value-free :class:`RdsrInputError` naming only an opaque exam
    position, the distinct-pair count, and — when some rows lack maker
    identity — that row count. Never maker/model text. Same-maker model
    variation, distinct canonical makers, and known+unknown mixes are all
    rejected: no row may silently borrow another row's identity, so the
    row-0 selection downstream only ever runs on a proven-homogeneous frame.
    ``exam_index`` is a 0-based exam position rendered through
    :func:`opaque_exam_label`; raw caller IDs are never accepted.
    """
    pairs = canonical_identity_pairs(frame)
    if len(pairs) <= 1:
        return
    label = opaque_exam_label(exam_index) if exam_index is not None else "exam"
    missing = missing_maker_rows(frame)
    detail = f" ({missing} event(s) without maker identity)" if missing else ""
    raise RdsrInputError(
        f"{label}: events carry {len(pairs)} distinct equipment identities "
        f"(manufacturer/model){detail}, which cannot share one normalization. "
        "Split the input so each exam covers one manufacturer and model."
    )
