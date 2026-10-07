"""Top-level settings container for a GUISkinDose run.

Aggregates mode, I/O, phantom, plot, normalization, kerma-meter, and
physics policy settings.
"""
import json
import logging
from pathlib import Path
from typing import Any, cast

from rich import print

from guiskindose.constants import (
    BELOW_FLOOR_KVP_POLICY_EXAM_AVERAGE,
    HVL_KVP_FLOOR,
    K_TAB_MODE_DEFAULT,
    K_TAB_MODES,
    KEY_PARAM_BEAM_MISS_WARN,
    KEY_PARAM_BELOW_FLOOR_KVP_MANUAL,
    KEY_PARAM_BELOW_FLOOR_KVP_POLICY,
    KEY_PARAM_ESTIMATE_K_TAB,
    KEY_PARAM_INHERENT_FILTRATION,
    KEY_PARAM_K_TAB_MODE,
    KEY_PARAM_K_TAB_VAL,
    KEY_PARAM_MODE,
    KEY_PARAM_RDSR_FILENAME,
    KEY_PARAM_REMOVE_INVALID_ROWS,
    KEY_PARAM_ROTATIONAL_ANGULAR_STEP,
    KEY_PARAM_ROTATIONAL_HANDLING,
    KEY_PARAM_ROTATIONAL_INCLUDE_STATIC,
    KEY_PARAM_SILENCE_PYDICOM_WARNINGS,
    ROTATIONAL_ANGULAR_STEP_DEFAULT,
    ROTATIONAL_ANGULAR_STEP_MAX,
    ROTATIONAL_ANGULAR_STEP_MIN,
    ROTATIONAL_HANDLING_COVERAGE,
    ROTATIONAL_HANDLING_MODES,
    RUN_ARGUMENTS_OUTPUT_DICT,
    RUN_ARGUMENTS_OUTPUT_HTML,
    RUN_ARGUMENTS_OUTPUT_JSON,
    RUN_ARGUMENTS_VALID_OUTPUT_FORMATS,
)

from .kerma_meter_correction_settings import KermaMeterCorrectionSettings
from .normalization_settings import NormalizationSettings
from .phantom_settings import PhantomSettings
from .plot_settings import Plotsettings

logger = logging.getLogger(__name__)

class PyskindoseSettings:
    """A class to store all settings required to run PySkinDose.

    Attributes
    ----------
    mode : str
        Select which mode to execute PySkinDose with. There are three
        different modes:

        mode = "calculate_dose" calculates the skin dose from the RDSR data and
        presents the result in a skin dose map.

        mode = "plot_setup" plots the geometry (patient, table, pad and beam
        in starting position, i.e., before any RDSR data has been added.) This
        is useful for debugging and when manually fixating the patient phantom
        with the function "position_patient_phantom_on_table".

        mode = "plot_event" plots the geometry for a specific irradiation event
        with index = event.

        mode = "plot_procedure" plots geometry of the entire sequence of RDSR
        events provided in the RDSR file. The patient phantom is omitted for
        calculation speed in human phantom is used.

    rdsr_filename : str
        filename of the RDSR file, without the .dcm file ending.
    k_tab_mode : str
        Patient-support transmission mode: ``measured_with_fallback`` (default; measured
        lookup per event, ``k_tab_val`` where no usable measured data exists),
        ``estimate`` (flat ``k_tab_val`` for every event), or ``measured_only``
        (measured lookup, ``1.0`` where it is unusable). The legacy ``estimate_k_tab``
        boolean is still read when ``k_tab_mode`` is absent (``True`` maps to
        ``estimate``, ``False`` to ``measured_only``) with a deprecation warning.
    k_tab_val : float
        Flat transmission factor in ``estimate`` mode and fallback value in
        ``measured_with_fallback`` mode. Must be finite and in ``(0, 1]``
        (``1.0`` means no attenuation).
    inherent_filtration : float
        X-ray tube inherent filtration, for backscatter and medium correction.
    below_floor_kvp_policy : str
        How to handle events with kVp below the HVL table floor (25 kV): one of
        "exam_average" (default, substitute the exam's mean in-floor kVp),
        "snap" (clamp to the grid edge), "skip" (drop the events), or
        "manual" (substitute ``below_floor_kvp_manual``).
    below_floor_kvp_manual : float
        kVp substituted for below-floor events when ``below_floor_kvp_policy`` is
        "manual".
    phantom : guiskindose.settings.phantom_settings.PhantomSettings
        Instance of class PhantomSettings containing all phantom related
        settings.
    plot : guiskindose.settings.plot_settings.Plotsettings
        Instance of class Plotsettings containing all plot related settings

    """

    def __init__(
        self,
        settings: str | dict,
        normalization_settings: Path | str | dict | NormalizationSettings | None = None,
        file_result_output_path: str | Path | None = None,
        output_format: str = RUN_ARGUMENTS_OUTPUT_HTML,
    ):
        """Initialize settings class.

        Parameters
        ----------
        settings : Union[str, dict]
            Either a JSON-string or a dictionary containing all the settings
            parameters required to run PySkinDose. See setting_example.json
            in /settings/ for example.

        """
        tmp = json.loads(settings) if isinstance(settings, str) else settings

        if (output_format := output_format.lower()) not in RUN_ARGUMENTS_VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"The output format must be specified as one of {', '.join(RUN_ARGUMENTS_VALID_OUTPUT_FORMATS)}"
            )

        self.mode = tmp[KEY_PARAM_MODE]
        self.output_format = output_format
        self.file_result_output_path: Path = self._initialize_output_path(
            output_path=file_result_output_path, output_format=output_format
        )
        self.k_tab_val = tmp[KEY_PARAM_K_TAB_VAL]
        self.inherent_filtration = tmp[KEY_PARAM_INHERENT_FILTRATION]
        self.silence_pydicom_warnings = tmp[KEY_PARAM_SILENCE_PYDICOM_WARNINGS]
        self.rdsr_filename = tmp[KEY_PARAM_RDSR_FILENAME]
        self.k_tab_mode: str = self._initialize_k_tab_mode(tmp)
        self.phantom = PhantomSettings(ptm_dim=tmp["phantom"])
        self.plot = Plotsettings(plt_dict=tmp["plot"])
        self.corrections_db_path = tmp.get("corrections_db_path", "corrections.db")

        self.normalization_settings = self._initialize_normalization_settings(normalization_settings)

        self.remove_invalid_rows: bool = bool(tmp.get(KEY_PARAM_REMOVE_INVALID_ROWS))

        # Below-floor kVp handling (kVp below the HVL table floor). Default
        # 'exam_average' substitutes the mean kVp of the exam for below-floor
        # events. See dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md.
        self.below_floor_kvp_policy: str = tmp.get(
            KEY_PARAM_BELOW_FLOOR_KVP_POLICY, BELOW_FLOOR_KVP_POLICY_EXAM_AVERAGE
        )
        self.below_floor_kvp_manual: float = float(
            tmp.get(KEY_PARAM_BELOW_FLOOR_KVP_MANUAL, HVL_KVP_FLOOR)
        )

        self.beam_miss_warn: str = tmp.get(KEY_PARAM_BEAM_MISS_WARN, "per_event")

        # Rotational-acquisition handling (coverage envelope by default).
        # Invalid values fail fast rather than silently degrading.
        rotational_handling = tmp.get(KEY_PARAM_ROTATIONAL_HANDLING, ROTATIONAL_HANDLING_COVERAGE)
        if rotational_handling not in ROTATIONAL_HANDLING_MODES:
            raise ValueError(
                f"rotational_handling must be one of {', '.join(ROTATIONAL_HANDLING_MODES)}"
            )
        self.rotational_handling: str = rotational_handling
        # Fail fast on non-bool input rather than coercing: bool("false") is
        # True, which would silently invert the caller's intent.
        include_static_pose = tmp.get(KEY_PARAM_ROTATIONAL_INCLUDE_STATIC, True)
        if not isinstance(include_static_pose, bool):
            raise ValueError("include_static_pose must be a boolean")
        self.include_static_pose: bool = include_static_pose
        angular_step_raw = tmp.get(KEY_PARAM_ROTATIONAL_ANGULAR_STEP, ROTATIONAL_ANGULAR_STEP_DEFAULT)
        # Require a real number before converting: bool is a subclass of int
        # (float(True) == 1.0, inside the accepted range) and float("5") would
        # silently coerce a string config value.
        if isinstance(angular_step_raw, bool) or not isinstance(angular_step_raw, (int, float)):
            raise ValueError(
                f"angular_step_deg must be a number, not a {type(angular_step_raw).__name__}"
            )
        angular_step = float(angular_step_raw)
        if not ROTATIONAL_ANGULAR_STEP_MIN <= angular_step <= ROTATIONAL_ANGULAR_STEP_MAX:
            raise ValueError(
                f"angular_step_deg must be within "
                f"{ROTATIONAL_ANGULAR_STEP_MIN}-{ROTATIONAL_ANGULAR_STEP_MAX} degrees"
            )
        self.angular_step_deg: float = angular_step

        km_raw = tmp.get("kerma_meter_correction")
        self.kerma_meter_correction = KermaMeterCorrectionSettings(
            km_raw if isinstance(km_raw, dict) else None
        )

        # Optional explicit DoseTrack Plane Code → meaning map for non-CID integers.
        from guiskindose.input_adapters.plane_code_map import parse_plane_code_map

        self.dosetrack_plane_code_map = parse_plane_code_map(tmp.get("dosetrack_plane_code_map"))

    @property
    def estimate_k_tab(self) -> bool:
        """Legacy read-only view of ``k_tab_mode`` (True only for ``estimate``)."""
        return self.k_tab_mode == "estimate"

    @staticmethod
    def _initialize_k_tab_mode(tmp: dict) -> str:
        """Resolve ``k_tab_mode``; map the legacy ``estimate_k_tab`` boolean when it is absent.

        An explicit ``k_tab_mode`` always wins. A legacy ``estimate_k_tab`` logs a
        deprecation warning. With neither key the default is ``measured_with_fallback``.

        Raises
        ------
        ValueError
            If ``k_tab_mode`` is not one of the three modes.
        """
        mode = tmp.get(KEY_PARAM_K_TAB_MODE)
        if mode is None:
            if KEY_PARAM_ESTIMATE_K_TAB not in tmp:
                return K_TAB_MODE_DEFAULT
            logger.warning(
                "estimate_k_tab is deprecated; use k_tab_mode (True maps to 'estimate', False to 'measured_only')."
            )
            return "estimate" if tmp[KEY_PARAM_ESTIMATE_K_TAB] else "measured_only"
        mode = str(mode).strip().lower()
        if mode not in K_TAB_MODES:
            raise ValueError(f"k_tab_mode must be one of {sorted(K_TAB_MODES)}")
        return mode

    def to_settings_dict(self) -> dict[str, Any]:
        """Return settings as a dict round-trippable through the constructor.

        The emitted shape matches `settings_example.json`
        (`PyskindoseSettings(settings=s.to_settings_dict())` reproduces `s`).
        `dosetrack_plane_code_map` integer keys are stringified for JSON
        safety; the constructor's `parse_plane_code_map` accepts int-like
        keys, so the map survives the round trip. Runtime-only state
        (`output_format`, `file_result_output_path`, `normalization_settings`,
        kerma `in_memory_table`) is intentionally excluded.

        Returns
        -------
        dict
            Settings dict in the `settings_example.json` shape.
        """
        plane_code_map = self.dosetrack_plane_code_map
        return {
            KEY_PARAM_MODE: self.mode,
            KEY_PARAM_RDSR_FILENAME: self.rdsr_filename,
            KEY_PARAM_K_TAB_MODE: self.k_tab_mode,
            KEY_PARAM_K_TAB_VAL: self.k_tab_val,
            KEY_PARAM_INHERENT_FILTRATION: self.inherent_filtration,
            KEY_PARAM_SILENCE_PYDICOM_WARNINGS: self.silence_pydicom_warnings,
            KEY_PARAM_REMOVE_INVALID_ROWS: self.remove_invalid_rows,
            KEY_PARAM_BELOW_FLOOR_KVP_POLICY: self.below_floor_kvp_policy,
            KEY_PARAM_BELOW_FLOOR_KVP_MANUAL: self.below_floor_kvp_manual,
            KEY_PARAM_BEAM_MISS_WARN: self.beam_miss_warn,
            KEY_PARAM_ROTATIONAL_HANDLING: self.rotational_handling,
            KEY_PARAM_ROTATIONAL_INCLUDE_STATIC: self.include_static_pose,
            KEY_PARAM_ROTATIONAL_ANGULAR_STEP: self.angular_step_deg,
            "corrections_db_path": self.corrections_db_path,
            "phantom": self.phantom.to_dict(),
            "plot": self.plot.to_dict(),
            "kerma_meter_correction": self.kerma_meter_correction.to_dict(),
            "dosetrack_plane_code_map": (
                None if plane_code_map is None else {str(code): meaning for code, meaning in plane_code_map.items()}
            ),
        }

    def to_json(self) -> str:
        """Return settings as a JSON string (see `to_settings_dict`).

        Returns
        -------
        str
            JSON-serialized settings dict.
        """
        return json.dumps(self.to_settings_dict())

    @staticmethod
    def _initialize_output_path(output_path: str | Path | None, output_format: str) -> Path:
        """Resolve the plot/output directory for the chosen output_format."""
        if output_path is None:
            output = Path.cwd() / "PlotOutputs"

            if output_format in (RUN_ARGUMENTS_OUTPUT_DICT, RUN_ARGUMENTS_OUTPUT_JSON):
                return output  # Return without creating the output directory as it won't be used

            output.mkdir(exist_ok=True)
            return output

        if isinstance(output_path, str):
            output_path = Path(output_path)

        if not isinstance(output_path, Path):
            raise TypeError("file_result_output_path must be a string or a Path object")

        if output_path.is_dir():
            return output_path

        raise ValueError("file_result_output_path must be a path to a directory")

    @staticmethod
    def _initialize_normalization_settings(
        normalization_settings: Path | str | dict | NormalizationSettings | None
    ) -> NormalizationSettings:
        """Load NormalizationSettings from path, dict, or existing instance."""
        if normalization_settings is None:
            normalization_settings = Path(__file__).parent.parent / "normalization_settings.json"

        if isinstance(normalization_settings, Path):
            normalization_settings = normalization_settings.read_text()

        if isinstance(normalization_settings, str):
            normalization_settings = json.loads(normalization_settings)

        if isinstance(normalization_settings, dict):
            settings_dict = normalization_settings
            if "normalization_settings" in settings_dict:
                settings_dict = settings_dict["normalization_settings"]
            normalization_settings = NormalizationSettings(cast(list[dict[str, Any]], settings_dict))

        if isinstance(normalization_settings, NormalizationSettings):
            return normalization_settings

        raise TypeError(f"Invalid type {type(normalization_settings)} given for normalization_settings")

    def print_parameters(self, return_as_string: bool = False):
        """Print entire parameter class to terminal.

        Parameters
        ----------
        return_as_string : bool, optional
            Return the print statement as a string, instead of printing it
            to the terminal. The default is False.

        """
        phantom_settings_string = self.phantom.to_printable_string(color="bright_magenta")
        plot_settings_string = self.plot.to_printable_string(color="steel_blue1")
        normalization_settings_string = self.normalization_settings.to_printable_string(color="bright_green")

        color = "bright_cyan"

        output_str = (
            f"[b u {color}]General settings[/b u {color}]\n"
            f"\t[{color}]mode:\t{self.mode}[/{color}]\n"
            f"\t[{color}]rdsr_filename:\t{self.rdsr_filename}[/{color}]\n"
            f"\t[{color}]k_tab_mode:\t{self.k_tab_mode}[/{color}]\n"
            f"\t[{color}]silence_pydicom_warnings:\t{'True' if self.silence_pydicom_warnings else 'False'}[/{color}]\n"
            f"\n{phantom_settings_string}"
            f"\n{plot_settings_string}"
            f"\n{normalization_settings_string}"
        )

        if return_as_string:
            return output_str

        return print(output_str)


def initialize_settings(settings: str | dict | PyskindoseSettings) -> PyskindoseSettings:
    """Coerce str/dict/settings input into a PyskindoseSettings instance."""
    valid_input_settings = settings is not None and isinstance(settings, (str, dict, PyskindoseSettings))

    if not valid_input_settings:
        raise ValueError("Settings must be given as a str or dict")

    if isinstance(settings, PyskindoseSettings):
        return settings

    return PyskindoseSettings(settings=settings)
