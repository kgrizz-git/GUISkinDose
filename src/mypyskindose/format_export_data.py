import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from mypyskindose.beam_class import Beam
from mypyskindose.constants import (
    KEY_NORMALIZATION_AIR_KERMA,
    OUTPUT_KEY_CORRECTION_BACK_SCATTER,
    OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW,
    OUTPUT_KEY_CORRECTION_KERMA_METER,
    OUTPUT_KEY_CORRECTION_MEDIUM,
    OUTPUT_KEY_CORRECTION_TABLE,
    OUTPUT_KEY_DOSE_MAP,
    OUTPUT_KEY_HITS,
    OUTPUT_KEY_KERMA_CORRECTED,
    PHANTOM_MODEL_HUMAN,
    PLOT_TRACE_ORDER_BEAM_WIREFRAME,
    PLOT_TRACE_ORDER_DETECTOR_WIREFRAME,
    PLOT_TRACE_ORDER_PHANTOM_WIREFRAME,
    RUN_ARGUMENTS_OUTPUT_DICT,
    RUN_ARGUMENTS_OUTPUT_JSON,
)
from mypyskindose.phantom_class import Phantom
from mypyskindose.settings import PyskindoseSettings

# Export JSON schema version — increment when ``PySkinDoseOutput.to_dict()`` (or
# ``MultiExamResult.to_dict()``) changes incompatibly: field removed, renamed, or
# type changed. Not tied to package semver; downstream consumers should read this
# before parsing nested fields.
EXPORT_SCHEMA_VERSION = 2


@dataclass
class Position:
    """Create and handle the x, y, and z-positions of, e.g., a phantom. When used for a phantom, each combination of an
    element of the same index in the x, y, and z-list represents the position of one skin cell.

    Attributes
    ----------
    x : list[float]
        A list of the x-positions, e.g., representing the x-position of a phantom's skin cells
    y : list[float]
        A list of the y-positions, e.g., representing the y-position of a phantom's skin cells
    z : list[float]
        A list of the z-positions, e.g., representing the x-position of a phantom's skin cells
    """

    x: list[float]
    y: list[float]
    z: list[float]

    def to_dict(self):
        """Serialize Position coordinates to a plain dict."""
        return {
            "x": [float(el) for el in self.x],
            "y": [float(el) for el in self.y],
            "z": [float(el) for el in self.z],
        }


@dataclass
class VertexIndices:
    """Create and handle the x, y, and z-positions of, e.g., a phantom. When used for a phantom, each combination of an
    element of the same index in the x, y, and z-list represents the position of one skin cell.

    Attributes
    ----------
    i : list[float]
        A list of the i-vertex indies, e.g., representing the i-vertex indices of a phantom's skin cells
    j : list[float]
        A list of the j-vertex indices, e.g., representing the j--vertex indices of a phantom's skin cells
    k : list[float]
        A list of the k-vertex indices, e.g., representing the k-vertex indices of a phantom's skin cells
    """

    i: list[float]
    j: list[float]
    k: list[float]

    def to_dict(self):
        """Serialize triangle vertex indices to a plain dict."""
        return {
            "i": [float(el) for el in self.i],
            "j": [float(el) for el in self.j],
            "k": [float(el) for el in self.k],
        }


class HumanPhantomOutput:
    """Create and handle a patient phantom data for output into a dict or JSON-string.

    Attributes
    ----------
    human_model : str
        The name of the human model used in the PySkinDose calculation
    phantom_skin_cells : Position
        The positions of all the phantom skin cells
    triangle_vertex_indices : VertexIndices
        The vertex indices of all the phantom skin cells
    r_ref : np.array
        The reference position of the phantom cells after the phantom has been aligned
        in the geometry with the position_patient_phantom_on_table function in geom_calc.py
    """

    def __init__(self, phantom: Phantom):
        """Capture human-phantom mesh geometry for export."""
        self.human_model = phantom.human_model
        self.phantom_skin_cells = Position(
            x=phantom.r[:, 0].tolist(), y=phantom.r[:, 1].tolist(), z=phantom.r[:, 2].tolist()
        )
        self.triangle_vertex_indices = VertexIndices(
            i=phantom.ijk[:, 0].tolist(), j=phantom.ijk[:, 1].tolist(), k=phantom.ijk[:, 2].tolist()
        )
        self.r_ref = phantom.r_ref

    def to_dict(self) -> dict:
        """Serialize human-phantom export fields to a dict."""
        return {
            "human_phantom": self.human_model,
            "r_ref": self.r_ref.tolist(),
            "patient_skin_cells": self.phantom_skin_cells.to_dict(),
            "triangle_vertex_indices": self.triangle_vertex_indices.to_dict(),
        }

    def to_json(self) -> str:
        """Serialize human-phantom export fields to JSON."""
        return json.dumps(self.to_dict())


class NonHumanPhantomOutput(HumanPhantomOutput):
    """Create and handle non-human phantoms, that is all phantoms that are not using a human model from, e.g., an
    stl-file.

    Attributes
    ----------
    phantom_skin_cells : Position
        The positions of all the phantom skin cells
    triangle_vertex_indices : VertexIndices
        The vertex indices of all the phantom skin cells
    """

    def __init__(self, phantom: Phantom):
        """Capture non-human (plane/cylinder) phantom geometry for export."""
        super().__init__(phantom)


class EventOutput:
    """Create and handle the data specifying an irradiation event, e.g., the positioning of the patient, table, pad, and
    beam.

    Attributes
    ----------
    events: int
        The number of events included in the PySkinDose calculation
    rotation : dict[str, list[float]]
        The x, y, and z rotation for each event
    translation : dict[str, list[float]]
        The x, y, and z translation for each event
    beam_positions : list[Position]
        The position of the beam for each event
    beam_vertex_indices : list[VertexIndices]
        The vertex indices of the beam for each event
    detector_positions : list[Position]
        The position of the detector for each event
    detector_vertex_indices : list[VertexIndices]
        The vertex indices of the detector for each event
    phantom_object_trace_order : list[int]
        The trace order to for the phantom object when creating plotly plots
    beam_wireframe_trace_order : list[int]
        The trace order to for the beam wireframes when creating plotly plots
    detector_wireframe_trace_order : list[int]
        The trace order to for the detector object when creating plotly plots
    """

    def __init__(self, data_norm: pd.DataFrame):
        """Extract per-event geometry fields from normalized RDSR data.

        An empty *data_norm* (e.g. after ``below_floor_kvp_policy=skip`` drops every
        event) yields empty geometry lists and empty setup meshes so dict/JSON export
        can still succeed with zero events.
        """
        self.events = len(data_norm)

        self.rotation = {
            "x": data_norm["Rx"].tolist() if self.events else [],
            "y": data_norm["Ry"].tolist() if self.events else [],
            "z": data_norm["Rz"].tolist() if self.events else [],
        }
        self.translation = {
            "x": data_norm.Tx.tolist() if self.events else [],
            "y": data_norm.Ty.tolist() if self.events else [],
            "z": data_norm.Tz.tolist() if self.events else [],
        }
        self.kerma = data_norm[KEY_NORMALIZATION_AIR_KERMA].tolist() if self.events else []
        self.phantom_object_trace_order = PLOT_TRACE_ORDER_PHANTOM_WIREFRAME
        self.beam_wireframe_trace_order = PLOT_TRACE_ORDER_BEAM_WIREFRAME
        self.detector_wireframe_trace_order = PLOT_TRACE_ORDER_DETECTOR_WIREFRAME

        if self.events == 0:
            empty_position = Position(x=[], y=[], z=[])
            empty_indices = VertexIndices(i=[], j=[], k=[])
            self.beam_positions = []
            self.beam_vertex_indices = []
            self.detector_positions = []
            self.detector_vertex_indices = []
            self.setup_beam_positions = empty_position
            self.setup_beam_vertex_indices = empty_indices
            self.setup_detector_positions = empty_position
            self.setup_detector_vertex_indices = empty_indices
            return

        self.beam_positions, self.beam_vertex_indices, self.detector_positions, self.detector_vertex_indices = zip(
            *[self._extract_beam_data_list(data_norm=data_norm, event=event) for event in range(len(data_norm))],
            strict=True,
        )
        (
            self.setup_beam_positions,
            self.setup_beam_vertex_indices,
            self.setup_detector_positions,
            self.setup_detector_vertex_indices,
        ) = self._extract_beam_data_list(data_norm=data_norm, event=0, setup=True)

    def _extract_position_list(self, phantom: Phantom, data_norm: pd.DataFrame) -> list[Position]:
        """Build a Position list for every event after positioning *phantom*."""
        return [
            self._get_position_dict(phantom=phantom, data_norm=data_norm, event=ind) for ind in range(len(data_norm))
        ]

    @staticmethod
    def _get_position_dict(phantom: Phantom, data_norm: pd.DataFrame, event: int) -> Position:
        """Position *phantom* for one event and return its vertex Position."""
        phantom.position(data_norm=data_norm, event=event)
        return Position(
            x=phantom.r[:, 0].tolist(),
            y=phantom.r[:, 1].tolist(),
            z=phantom.r[:, 2].tolist(),
        )

    @staticmethod
    def _extract_beam_data_list(
        data_norm: pd.DataFrame, event: int, setup: bool = False
    ) -> tuple[Position, VertexIndices, Position, VertexIndices]:
        """Extract beam mesh Position/index data for one irradiation event."""
        beam = Beam(data_norm, event=event, plot_setup=setup)
        beam_position = Position(x=beam.r[:, 0].tolist(), y=beam.r[:, 1].tolist(), z=beam.r[:, 2].tolist())
        beam_vertex_indices = VertexIndices(
            i=beam.ijk[:, 0].tolist(), j=beam.ijk[:, 1].tolist(), k=beam.ijk[:, 2].tolist()
        )
        detector_position = Position(
            x=beam.det_r[:, 0].tolist(), y=beam.det_r[:, 1].tolist(), z=beam.det_r[:, 2].tolist()
        )
        detector_vertex_indices = VertexIndices(
            i=beam.det_ijk[:, 0].tolist(), j=beam.det_ijk[:, 1].tolist(), k=beam.det_ijk[:, 2].tolist()
        )

        return beam_position, beam_vertex_indices, detector_position, detector_vertex_indices

    def to_dict(self):
        """Serialize event geometry fields to a plain dict."""
        return {
            "number_of_events": self.events,
            "rotation": self.rotation,
            "translation": self.translation,
            "kerma": self.kerma,
            "phantom_object_trace_order": self.phantom_object_trace_order,
            "beam": {
                "positions": [pos.to_dict() for pos in self.beam_positions],
                "vertex_indices": [pos.to_dict() for pos in self.beam_vertex_indices],
                "trace_order": self.beam_wireframe_trace_order,
                "setup": {
                    "position": self.setup_beam_positions.to_dict(),
                    "vertex_indices": self.setup_beam_vertex_indices.to_dict(),
                },
            },
            "detector": {
                "positions": [pos.to_dict() for pos in self.detector_positions],
                "vertex_indices": [pos.to_dict() for pos in self.detector_vertex_indices],
                "trace_order": self.detector_wireframe_trace_order,
                "setup": {
                    "position": self.setup_detector_positions.to_dict(),
                    "vertex_indices": self.setup_detector_vertex_indices.to_dict(),
                },
            },
        }


# eq=False keeps identity-based equality/hashing (the pre-dataclass behaviour).
# A generated __eq__ would compare ndarray/DataFrame fields (dose_map, data_norm)
# element-wise and raise "ambiguous truth value", and would also make instances
# unhashable.
@dataclass(eq=False)
class PySkinDoseOutput:
    """A collection of the information resulting from the PySkinDose analysis

    Attributes
    __________

    psd : float
        The peak skin dose found in the dose map
    air_kerma : float
        The total air KERMA of the
    events : EventOutput
        The event data for the examination
    patient : Phantom
        The patient phantom used in the calculations.
    patient_export() : dict[str, str | HumanPhantomOutput | NonHumanPhantomOutput]
        Build the serialized patient envelope used by ``to_dict()`` and rich export.
    patient_offsets : dict[str, float]
        The base offsets in the long, vert, and lat direction
    table : Phantom
        The treatment table as an instance of the Phantom class
    pad : Phantom
        The treatment table pad as an instance of the Phantom class
    pad_thickness : float
        The thickness of the treatment table pad
    dose_map : np.ndarray
        The total dose map given as a numpy array where the values correspond to the resulting dose in Gy
    sparse_hit_indices() : list[list[int]]
        Build one cell-index list for each radiation event, aligned with correction arrays.
    backscatter_correction : list[list[float]]
        The backscatter corrections used for each cell hit given as a list of floats where the event and cell index of
        each float is given by getting the same list index element from ``sparse_hit_indices()``.
    inverse_square_law_correction : list[float]
        The inverse square law corrections used for each cell hit given as a list of floats where the event and cell
        index of each float is given by getting the same list index element from ``sparse_hit_indices()``.
    medium_correction : list[float]
        The corrections for the irradiated medium/-s used for each cell hit given as a list of floats where the event
        and cell index of each float is given by getting the same list index element from ``sparse_hit_indices()``.
    table_correction : list[float]
        The corrections for the treatment table used for each cell hit given as a list of floats where the event and
        cell index of each float is given by getting the same list index element from ``sparse_hit_indices()``.

    """

    patient: Phantom
    table: Phantom
    pad: Phantom
    dose_map: np.ndarray
    hits: list[list[float]]
    backscatter_correction: list[list[float]]
    inverse_square_law_correction: list[list[float] | float]
    medium_correction: list[float]
    table_correction: list[float]
    settings: PyskindoseSettings
    data_norm: pd.DataFrame
    kerma_meter_correction: list[float] | None = None
    kerma_corrected: list[float] | None = None

    # Derived canonical values — legacy uppercase attribute aliases are intentionally absent.
    psd: float = field(init=False)
    air_kerma: float = field(init=False)
    events: "EventOutput" = field(init=False)
    air_kerma_corrected: float = field(init=False)
    patient_offsets: dict[str, float] = field(init=False)
    pad_thickness: float = field(init=False)

    def __post_init__(self) -> None:
        """Validate inputs and compute the derived export fields."""
        n_events = len(self.data_norm)
        self._validate_lengths(n_events)
        self._compute_derived(n_events)

    def _validate_lengths(self, n_events: int) -> None:
        """Reject mismatched list lengths with a ValueError naming the offending field."""
        error = False
        error_message: list[str] = [""]

        if len(self.hits) != n_events:
            error = True
            error_message.append(
                "Hits:\n"
                "\tThe hits list is not the same length as the number of normalized events"
            )

        if len(self.backscatter_correction) != len(self.hits):
            error = True
            error_message.append(
                "Backscatter correction:\n"
                "\tThe backscatter correction list is not the same length as the number of events"
            )

        if len(self.inverse_square_law_correction) != len(self.hits):
            error = True
            error_message.append(
                "Inverse square law correction:\n"
                "\tThe inverse square law correction list is not the same length as the number of events"
            )

        if len(self.medium_correction) != len(self.hits):
            error = True
            error_message.append(
                "Medium correction:\n"
                "\tThe medium correction list is not the same length as the number of events"
            )

        if len(self.table_correction) != len(self.hits):
            error = True
            error_message.append(
                "Table correction:\n"
                "\tThe table correction list is not the same length as the number of events"
            )

        has_kerma_meter = self.kerma_meter_correction is not None
        has_kerma_corrected = self.kerma_corrected is not None
        if has_kerma_meter != has_kerma_corrected:
            error = True
            error_message.append(
                "Kerma correction:\n"
                "\tkerma_meter_correction and kerma_corrected must both be provided or both omitted"
            )

        if self.kerma_meter_correction is not None and len(self.kerma_meter_correction) != n_events:
            error = True
            error_message.append(
                "Kerma-meter correction:\n"
                "\tThe kerma-meter correction list is not the same length as the number of events"
            )

        if self.kerma_corrected is not None and len(self.kerma_corrected) != n_events:
            error = True
            error_message.append(
                "Kerma corrected:\n"
                "\tThe kerma-corrected list is not the same length as the number of events"
            )

        if error:
            raise ValueError("\n\n".join(error_message))

    def _compute_derived(self, n_events: int) -> None:
        """Populate canonical derived values after validation passes."""
        self.psd = float(self.dose_map.max())
        self.air_kerma = float(self.data_norm[KEY_NORMALIZATION_AIR_KERMA].sum())
        self.events = EventOutput(data_norm=self.data_norm)
        kerma_meter_correction = self.kerma_meter_correction
        kerma_corrected = self.kerma_corrected
        if kerma_meter_correction is None and kerma_corrected is None:
            self.kerma_meter_correction = [1.0] * n_events
            self.kerma_corrected = list(self.events.kerma)
        elif kerma_meter_correction is not None and kerma_corrected is not None:
            self.kerma_meter_correction = [float(v) for v in kerma_meter_correction]
            self.kerma_corrected = [float(v) for v in kerma_corrected]
        else:
            # _validate_lengths() rejects this pair, but retain a clear invariant
            # failure if this method is ever called independently.
            raise ValueError("kerma_meter_correction and kerma_corrected must be paired")
        self.air_kerma_corrected = float(sum(self.kerma_corrected))
        self.patient_offsets = {
            "long": self.settings.phantom.patient_offset.d_lon,
            "vert": self.settings.phantom.patient_offset.d_ver,
            "lat": self.settings.phantom.patient_offset.d_lat,
        }
        self.pad_thickness = float(self.settings.phantom.dimension.pad_thickness)

    def patient_export(self) -> dict[str, str | HumanPhantomOutput | NonHumanPhantomOutput]:
        """Build the patient envelope used by serialized and rich exports."""
        return {
            "patient_type": self.patient.phantom_model,
            "patient": (
                HumanPhantomOutput(self.patient)
                if self.patient.phantom_model == PHANTOM_MODEL_HUMAN
                else NonHumanPhantomOutput(self.patient)
            ),
            "orientation": self.settings.phantom.patient_orientation,
        }

    def sparse_hit_indices(self) -> list[list[int]]:
        """Build sparse hit-cell indices aligned with per-event corrections."""
        return [
            [ind for ind, hit in enumerate(event_hits) if hit]
            for event_hits in self.hits
        ]

    def to_dict(self) -> dict[str, Any]:
        """Converts the output data into a dict

        Returns
        -------
        Dict[str, Any]
            A dict containing the output data for the PySkinDose analysis where the lists of hits and corrections have
            been made sparse in order to save space.
        """
        patient_export = self.patient_export()
        patient = patient_export["patient"]
        if not isinstance(patient, (HumanPhantomOutput, NonHumanPhantomOutput)):
            raise TypeError("patient_export() returned an unsupported patient payload")
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "psd": self.psd,
            "air_kerma": self.air_kerma,
            "air_kerma_corrected": self.air_kerma_corrected,
            "patient": {
                "patient_type": patient_export["patient_type"],
                "patient": patient.to_dict(),
                "orientation": patient_export["orientation"],
                "offsets": self.patient_offsets,
            },
            "table": {
                "table_surface": {
                    "x": self.table.r[:, 0].tolist(),
                    "y": self.table.r[:, 1].tolist(),
                    "z": self.table.r[:, 2].tolist(),
                },
                "triangle_vertex_indices": {
                    "i": self.table.ijk[:, 0].tolist(),
                    "j": self.table.ijk[:, 1].tolist(),
                    "k": self.table.ijk[:, 2].tolist(),
                },
                "table_length": self.table.table_length,
            },
            "pad": {
                "pad_surface": {
                    "x": self.pad.r[:, 0].tolist(),
                    "y": self.pad.r[:, 1].tolist(),
                    "z": self.pad.r[:, 2].tolist(),
                },
                "triangle_vertex_indices": {
                    "i": self.pad.ijk[:, 0].tolist(),
                    "j": self.pad.ijk[:, 1].tolist(),
                    "k": self.pad.ijk[:, 2].tolist(),
                },
            },
            "dose_map": [(ind, dose) for ind, dose in enumerate(self.dose_map.tolist()) if dose > 0.0],
            "corrections": {
                "correction_value_index": self.sparse_hit_indices(),
                "backscatter": self.backscatter_correction,
                "medium": self.medium_correction,
                "table": self.table_correction,
                "inverse_square_law": self.inverse_square_law_correction,
                "kerma": self.events.to_dict().get("kerma", []),
                "kerma_corrected": self.kerma_corrected,
                "kerma_meter": self.kerma_meter_correction,
            },
            "events": self.events.to_dict(),
        }

    def to_json(self) -> str:
        """Converts the output data into a JSON string

        Returns
        -------
        str
            A JSON formatted string containing the output data
        """
        return json.dumps(self.to_dict())

    def __repr__(self) -> str:
        def safe_number(name: str) -> str:
            value = getattr(self, name, "<unavailable>")
            try:
                return f"{value:.4f}"
            except (TypeError, ValueError):
                return "<unavailable>"

        return (
            f"PySkinDoseOutput(psd={safe_number('psd')}, air_kerma={safe_number('air_kerma')}, "
            f"air_kerma_corrected={safe_number('air_kerma_corrected')}, pad_thickness={safe_number('pad_thickness')}, "
            f"patient_offsets={getattr(self, 'patient_offsets', '<unavailable>')!r})"
        )


@dataclass
class ExamResult:
    """Per-exam wrapper around PySkinDoseOutput with run metadata."""

    exam_id: str
    source_file: str
    event_count: int
    patient_offset: list[float]
    settings_snapshot: dict[str, Any]
    output: PySkinDoseOutput
    warnings: list[str]


@dataclass
class MultiExamResult:
    """Result of a multi-exam run: per-exam outputs plus an aggregate dose map.

    ``exams_attempted`` / ``exams_excluded`` record how many loaded exams were
    processed vs omitted from the aggregate (exception or no-output paths).
    """

    exams: list[ExamResult]
    aggregate_dose_map: np.ndarray
    aggregate_psd: float
    total_events: int
    warnings: list[str]
    exams_attempted: int = 0
    exams_excluded: int = 0

    def to_dict(self, *, include_source_identifiers: bool = False) -> dict[str, Any]:
        """Serialize results, excluding source filenames by default."""
        exams: list[dict[str, Any]] = []
        for exam in self.exams:
            serialized = {
                "exam_id": exam.exam_id,
                "event_count": exam.event_count,
                "patient_offset": exam.patient_offset,
                "settings_snapshot": exam.settings_snapshot,
                "warnings": exam.warnings,
                "output": exam.output.to_dict(),
            }
            if include_source_identifiers:
                serialized["source_file"] = exam.source_file
            exams.append(serialized)
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "exams": exams,
            "aggregate_dose_map": self.aggregate_dose_map.tolist(),
            "aggregate_psd": self.aggregate_psd,
            "total_events": self.total_events,
            "warnings": self.warnings,
            "exams_attempted": self.exams_attempted,
            "exams_excluded": self.exams_excluded,
        }

    def to_json(self, *, include_source_identifiers: bool = False) -> str:
        """Serialize this MultiExamResult to a JSON string."""
        return json.dumps(self.to_dict(include_source_identifiers=include_source_identifiers))


def format_analysis_result_for_export(
    analysis_result: dict[str, Any],
    data_norm: pd.DataFrame,
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    settings: PyskindoseSettings,
) -> PySkinDoseOutput | dict[str, Any] | str:
    """Formats the result of the PySkinDose analysis into a PySkinDoseOutput class instance that has a methods for
    converting the result to either a dict or a JSON string to facilitate building custom visualizations and for other
    custom implementations of the PySkinDose calculated data.

    Parameters
    ----------
    analysis_result : dict[str, Any]
        The dict resulting from the call to mypyskindose.calculate_dose.calculate_dose.calculate_dose
    data_norm : pd.DataFrame
        The RDSR data, normalized for compliance with PySkinDose's use of units etc.
    patient : Phantom
        An instance of the Phantom class that represents the patient
    table : Phantom
        An instance of the Phantom class that represents the treatment table
    pad : Phantom
        An instance of the Phantom class that represents the pad
    settings : PyskindoseSettings
        The instance of the settings class used in the PySkinDose run for the current data

    Returns
    -------
    Union[PySkinDoseOutput, dict[str, Any], str]
        The PySkinDose formatted output as either a PySkinDoseOutput class instance, a dict or a JSON-formatted string
        depending on the output format specified in the settings
    """
    mypyskindose_output = PySkinDoseOutput(
        patient=patient,
        table=table,
        pad=pad,
        dose_map=analysis_result[OUTPUT_KEY_DOSE_MAP],
        hits=[event if isinstance(event, list) else event.tolist() for event in analysis_result[OUTPUT_KEY_HITS]],
        backscatter_correction=[
            event if isinstance(event, list) else event.tolist()
            for event in analysis_result[OUTPUT_KEY_CORRECTION_BACK_SCATTER]
        ],
        inverse_square_law_correction=[
            event if isinstance(event, (list, float)) else ([] if event is None else event.tolist())
            for event in analysis_result[OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW]
        ],  # type: ignore[arg-type]
        medium_correction=analysis_result[OUTPUT_KEY_CORRECTION_MEDIUM],
        table_correction=analysis_result[OUTPUT_KEY_CORRECTION_TABLE],
        settings=settings,
        data_norm=data_norm,
        kerma_meter_correction=analysis_result.get(OUTPUT_KEY_CORRECTION_KERMA_METER),
        kerma_corrected=analysis_result.get(OUTPUT_KEY_KERMA_CORRECTED),
    )

    if settings.output_format == RUN_ARGUMENTS_OUTPUT_DICT:
        return mypyskindose_output.to_dict()

    if settings.output_format == RUN_ARGUMENTS_OUTPUT_JSON:
        return mypyskindose_output.to_json()

    return mypyskindose_output
