import re
from typing import Any

import pandas as pd

from mypyskindose.constants import (
    KEY_NORMALIZATION_DETECTOR_SIDE_LENGTH,
    KEY_NORMALIZATION_FIELD_SIZE_MODE,
    KEY_NORMALIZATION_MANUFACTURER,
    KEY_NORMALIZATION_MODELS,
    KEY_RDSR_MANUFACTURER,
    KEY_RDSR_MANUFACTURER_MODEL_NAME,
)
from mypyskindose.debug import dprint
from mypyskindose.helpers.create_attributes_string import create_attributes_string
from mypyskindose.settings.rotation_direction import RotationDirection
from mypyskindose.settings.translation_direction import TranslationDirection
from mypyskindose.settings.translation_offset import TranslationOffset

_GE_MANUFACTURER_ALIASES = frozenset(
    {
        "ge",
        "gehealthcare",
        "ge healthcare",
        "ge medical systems",
        "general electric",
        "gems",
    }
)

_MANUFACTURER_ALIASES_BY_SETTINGS_KEY = {
    "ge healthcare": _GE_MANUFACTURER_ALIASES,
    "siemens": frozenset(
        {
            "siemens",
            "siemens healthcare",
            "siemens healthineers",
            "siemens medical solutions",
            "siemens ag",
        }
    ),
    "philips": frozenset(
        {
            "philips",
            "philips healthcare",
            "philips medical systems",
            "philips medical systems nederland b v",
            "philips medical systems nederland bv",
        }
    ),
}


def normalize_manufacturer_key(manufacturer: object) -> str:
    """Canonical manufacturer key for settings lookup and vendor detection."""
    key = re.sub(r"[^0-9a-z]+", " ", str(manufacturer).casefold()).strip()
    return " ".join(key.split())


def normalize_model_key(model: object) -> str:
    """Canonical model key for settings lookup."""
    if str(model).strip() == "*":
        return "*"
    key = re.sub(r"[^0-9a-z]+", " ", str(model).casefold()).strip()
    return " ".join(key.split())


def _manufacturer_matches(input_manufacturer: str, settings_manufacturer: str) -> bool:
    if input_manufacturer == settings_manufacturer:
        return True
    return input_manufacturer in _MANUFACTURER_ALIASES_BY_SETTINGS_KEY.get(settings_manufacturer, frozenset())


class NormalizationSettings:
    """A class to normalize RDSR for PySkinDose compliance.

    Attributes
    ----------
    trans_offset : mypyskindose.settings.translation_offset.TranslationOffset
        See class variables of _TranslationOffset
    trans_dir : mypyskindose.settings.translation_direction.TranslationDirection
        See class variables of _TranslationDirection
    rot_dir : mypyskindose.settings.rotation_direction.RotationDirection
        See class variables of _RotationDirection
    field_size_mode : str
        method for calculating field size at image receptor plane.
        Choose either "CFA" (collimated field area) or "ACD" (actual shutter
        distance). For more info, see calculate_field_size in geom_calc.py.
    detector_side_length : str
        side length of active image receptor area in cm.
    swap_lateral_longitudinal : bool
        If true, swap raw TableLongitudinalPosition and TableLateralPosition
        values before deriving Tx/Tz. Used for GE's high-confidence RDSR-level
        lateral/longitudinal convention.

    """

    def __init__(self, normalization_settings: list[dict[str, Any]]):
        """Initialize class attributes."""
        self.normalization_settings_list: list[dict[str, Any]] = normalization_settings
        self.trans_offset: TranslationOffset = TranslationOffset()
        self.trans_dir: TranslationDirection = TranslationDirection()
        self.rot_dir: RotationDirection = RotationDirection()
        self.field_size_mode: str | None = None
        self.detector_side_length: str | None = None
        self.normalization_method: str = "Unknown"
        self.matched_manufacturer: str = ""
        self.matched_model: str = ""
        self.swap_lateral_longitudinal: bool = False

        self.attrs_str = create_attributes_string(attrs_parent=self, object_name="normalization", indent_level=0)

    def update_used_settings(self, data_parsed: pd.DataFrame):
        manufacturer = normalize_manufacturer_key(data_parsed[KEY_RDSR_MANUFACTURER][0])
        model = normalize_model_key(data_parsed[KEY_RDSR_MANUFACTURER_MODEL_NAME][0])

        manufacturer_settings = [
            setting
            for setting in self.normalization_settings_list
            if _manufacturer_matches(
                manufacturer,
                normalize_manufacturer_key(setting[KEY_NORMALIZATION_MANUFACTURER]),
            )
        ]
        setting = [
            setting
            for setting in manufacturer_settings
            if model in [normalize_model_key(mod) for mod in setting[KEY_NORMALIZATION_MODELS]]
        ]
        if not setting:
            setting = [
                setting
                for setting in manufacturer_settings
                if "*" in [normalize_model_key(mod) for mod in setting[KEY_NORMALIZATION_MODELS]]
            ]

        if not setting:
            dprint("PROCESSING", f"No specific match for {manufacturer} {model}. Looking for 'Default'...")
            setting = [
                setting
                for setting in self.normalization_settings_list
                if "default" == setting[KEY_NORMALIZATION_MANUFACTURER].casefold()
            ]
            self.normalization_method = "Fallback"
        else:
            self.normalization_method = "Matched"

        if not setting:
            self.normalization_method = "None"
            raise NotImplementedError(
                f"Could not find settings for the given manufacturer and model ({manufacturer=}, {model=}) and no 'Default' entry found."
            )

        setting = setting[0]
        self.matched_manufacturer = setting[KEY_NORMALIZATION_MANUFACTURER]
        self.matched_model = setting[KEY_NORMALIZATION_MODELS][0] if setting[KEY_NORMALIZATION_MODELS] else "N/A"

        dprint(
            "PROCESSING",
            f"Normalization: {self.normalization_method} (Matched: {self.matched_manufacturer} - {self.matched_model})",
        )
        dprint("PROCESSING", f"Applied offsets: {setting.get('translation_offset')}")

        if translation_offset := setting.get("translation_offset"):
            self.trans_offset.update_translation_offset(offset=translation_offset)
        if translation_direction := setting.get("translation_direction"):
            self.trans_dir.update_translation_direction(directions=translation_direction)
        if rotation_direction := setting.get("rotation_direction"):
            self.rot_dir.update_rotation_direction(directions=rotation_direction)
        self.field_size_mode = setting[KEY_NORMALIZATION_FIELD_SIZE_MODE]
        self.detector_side_length = setting[KEY_NORMALIZATION_DETECTOR_SIDE_LENGTH]
        self.swap_lateral_longitudinal = bool(setting.get("swap_lateral_longitudinal", False))

        self.update_attrs_str()

    def update_attrs_str(self):
        self.attrs_str = create_attributes_string(attrs_parent=self, object_name="normalization", indent_level=0)

    def to_printable_string(self, color: str = "blue"):
        return (
            f"[bold {color}]Normalization settings[/bold {color}]\n"
            f"\t[{color}]trans_offset:[/{color}]\n"
            f"\t\t[{color}]x:{self.trans_offset.x}[/{color}]\n"
            f"\t\t[{color}]y:{self.trans_offset.y}[/{color}]\n"
            f"\t\t[{color}]z:{self.trans_offset.z}[/{color}]\n"
            f"\t[{color}]trans_dir:[/{color}]\n"
            f"\t\t[{color}]x:{self.trans_dir.x}[/{color}]\n"
            f"\t\t[{color}]y:{self.trans_dir.y}[/{color}]\n"
            f"\t\t[{color}]z:{self.trans_dir.z}[/{color}]\n"
            f"\t[{color}]rot_dir:[/{color}]\n"
            f"\t\t[{color}]Ap1:{self.rot_dir.Ap1}[/{color}]\n"
            f"\t\t[{color}]Ap2:{self.rot_dir.Ap2}[/{color}]\n"
            f"\t\t[{color}]Ap3:{self.rot_dir.Ap3}[/{color}]\n"
            f"\t\t[{color}]At1:{self.rot_dir.At1}[/{color}]\n"
            f"\t\t[{color}]At2:{self.rot_dir.At2}[/{color}]\n"
            f"\t\t[{color}]At3:{self.rot_dir.At3}[/{color}]\n"
            f"\t[{color}]field_size_mode: {self.field_size_mode}[/{color}]\n"
            f"\t[{color}]detector_side_length: {self.detector_side_length}[/{color}]\n"
            f"\t[{color}]swap_lateral_longitudinal: {self.swap_lateral_longitudinal}[/{color}]\n"
        )
