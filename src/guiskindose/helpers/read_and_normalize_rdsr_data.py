"""Read an RDSR file and return the internal event DataFrame.

For DICOM RDSR inputs, parses with pydicom, normalizes vendor conventions,
and optionally drops invalid kVp rows. For ``.json`` inputs, returns the
pre-parsed frame via ``pd.read_json`` without re-running the normalizer.

A validated captured-coordinate authority replays DICOM normalization
offline: the captured recipe lands on a private settings clone before
concept validation, live bundled selection is bypassed entirely, and the
final frame is confirmed before it is returned. Preparsed JSON inputs refuse
a capture, since there is no raw normalization to replay.
"""
import logging
from pathlib import Path

import pandas as pd
import pydicom

from guiskindose.equipment_confirmation import (
    confirm_captured_application,
    prepare_replay_settings,
)
from guiskindose.equipment_profiles.capture import (
    CODE_INVALID_EQUIPMENT_CAPTURE,
    CapturedCoordinates,
    CaptureError,
    validate_constructed_context,
)
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def _reject_captured_conflicts(
    settings: PyskindoseSettings,
    equipment_receipt_out: list | None,
    equipment_capture_context: CapturedCoordinates,
) -> None:
    """Full context validation plus authority-conflict rejection before any I/O.

    A constructor-bypassed forgery fails here with zero source reads; live
    sessions and receipt lists are refused on the same closed terms.
    """
    try:
        validate_constructed_context(equipment_capture_context)
    except (TypeError, AttributeError):
        raise CaptureError(
            "Equipment capture context must be a CapturedCoordinates or None.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise CaptureError(
            "Equipment capture replay never resolves a live session.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )
    if equipment_receipt_out is not None:
        raise CaptureError(
            "Equipment capture replay never publishes receipt records.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        )


def read_and_normalise_rdsr_data(
    rdsr_filepath: str | None,
    settings: PyskindoseSettings,
    *,
    equipment_receipt_out: list | None = None,
    equipment_capture_context: CapturedCoordinates | None = None,
) -> pd.DataFrame:
    """Load RDSR event data for downstream dose calculations.

    DICOM paths are parsed and normalized; ``.json`` paths are loaded as
    stored (already normalized when exported).

    Parameters
    ----------
    rdsr_filepath : str | None
        Explicit path to an RDSR DICOM or JSON file. When *None*, the path
        is derived from *settings.rdsr_filename* in the bundled example
        data directory.
    settings : PyskindoseSettings
        Runtime settings controlling parsing and normalization behavior.
    equipment_receipt_out : list | None
        Optional list receiving the custom equipment-profile resolution
        record (when a session is bound on settings), else left untouched.
        Refused together with a capture context: replay never publishes.
    equipment_capture_context : CapturedCoordinates | None
        Validated captured-coordinate authority for offline DICOM replay.
        The DICOM source is still read and parsed; the captured recipe is
        applied to a private settings clone before concept validation,
        bundled selection is bypassed, and the post-filter frame is confirmed
        before it is returned. Refused on preparsed JSON inputs, with a live
        session bound, or with a receipt list supplied — all before any I/O.

    Returns
    -------
    pd.DataFrame
        Event DataFrame ready for geometry reconstruction and dose
        accumulation (normalized for DICOM; as stored for JSON).
    """
    if equipment_capture_context is not None:
        _reject_captured_conflicts(settings, equipment_receipt_out, equipment_capture_context)
    path: Path = (
        Path(rdsr_filepath)
        if rdsr_filepath
        else Path(__file__).parent.parent / "example_data/RDSR" / settings.rdsr_filename
    )

    # Log only the file type, never the path/name — RDSR filenames routinely
    # contain PHI (patient name, MRN, accession) in clinical use.
    logger.debug("Reading RDSR data from a %s file", path.suffix.lower() or "(no suffix)")

    # If provided, load preparsed rdsr data in .json format
    if path.suffix.lower() == ".json":
        if equipment_capture_context is not None:
            raise CaptureError(
                "Equipment capture replay needs raw DICOM input, not preparsed JSON.",
                CODE_INVALID_EQUIPMENT_CAPTURE,
            )
        from guiskindose.equipment_resolution import check_session_input_compatible

        check_session_input_compatible(
            schema="preparsed_json",
            session=getattr(settings, "equipment_profile_session", None),
        )
        return pd.read_json(path)

    # else load RDSR data with pydicom
    data_raw = pydicom.dcmread(path)

    # parse RDSR data from raw .dicom file
    data_parsed = rdsr_parser(data_raw, silence_pydicom_warnings=settings.silence_pydicom_warnings)

    if equipment_capture_context is None:
        # normalized rdsr for compliance with PySkinDose
        receipts: list = []
        normalized_data = rdsr_normalizer(data_parsed, settings=settings, equipment_receipt_out=receipts)

        if settings.remove_invalid_rows and (invalid_kvp_rows := len(normalized_data[normalized_data.kVp == 0])):
            print(f"Removing {invalid_kvp_rows} rows with kVp value = 0")
            normalized_data = normalized_data[normalized_data.kVp != 0].reset_index(drop=True)

        if equipment_receipt_out is not None and receipts:
            from guiskindose.equipment_resolution import bind_receipt_frame

            equipment_receipt_out.append(bind_receipt_frame(receipts[0], normalized_data))
        return normalized_data

    return _replay_captured_frame(data_parsed, settings, equipment_capture_context)


def _replay_captured_frame(
    data_parsed: pd.DataFrame, settings: PyskindoseSettings, context: CapturedCoordinates
) -> pd.DataFrame:
    """Replay raw normalization from a capture onto private settings, then confirm.

    The recipe lands before concept validation, bundled selection is
    bypassed, and final confirmation runs only after the existing invalid-row
    policy. Mismatch fails closed, publishing nothing and leaving the
    caller's settings untouched; only a confirmed frame is returned.
    """
    work_settings = prepare_replay_settings(context=context, settings=settings)
    try:
        replayed_data = rdsr_normalizer(
            data_parsed,
            work_settings,
            equipment_receipt_out=None,
            equipment_capture_context=context,
        )
    except CaptureError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError):
        raise CaptureError(
            "Equipment capture replay failed closed during normalization.",
            CODE_INVALID_EQUIPMENT_CAPTURE,
        ) from None
    if work_settings.remove_invalid_rows and (invalid_kvp_rows := len(replayed_data[replayed_data.kVp == 0])):
        print(f"Removing {invalid_kvp_rows} rows with kVp value = 0")
        replayed_data = replayed_data[replayed_data.kVp != 0].reset_index(drop=True)
    # Final confirmation only, after the existing invalid-row policy: the
    # receipt and mapping it validates are dropped — a confirmed frame is the
    # only product. Mismatch fails closed, publishing nothing.
    confirm_captured_application(
        context=context,
        frame=replayed_data,
        candidate=work_settings.normalization_settings,
    )
    return replayed_data
