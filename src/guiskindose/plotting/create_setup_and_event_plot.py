"""Assemble meshes, wireframes, and layout for setup or single-event plots."""
import logging

import plotly.graph_objects as go

from ..beam_class import Beam
from ..constants import (
    COLOR_BEAM,
    COLOR_DETECTOR,
    COLOR_PAD,
    COLOR_PATIENT,
    COLOR_SOURCE,
    COLOR_TABLE,
    MESH_NAME_PAD,
    MESH_OPACITY_BEAM,
    PLOT_LIGHTNING_AMBIENT,
    PLOT_LIGHTNING_DIFFUSE,
    PLOT_SOURCE_SIZE,
    PLOT_WIREFRAME_LINE_WIDTH,
)
from ..phantom_class import Phantom
from .create_mesh3d import create_mesh_3d_general
from .create_plot_and_save_to_file import create_plot_and_save_to_file
from .create_wireframes import create_wireframes
from .plot_layout import default_geometry_layout

logger = logging.getLogger(__name__)


def create_setup_and_event_plot(
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    beam: Beam,
    mode: str,
    patient_text: list[str],
    source_text: list[str],
    table_text: list[str],
    detectors_text: list[str],
    pad_text: list[str],
    beam_text: list[str],
    title: str,
    dark_mode=True,
    notebook_mode: bool = False,
):
    """Assemble meshes, wireframes and layout for setup or event plots.

    Parameters
    ----------
    patient : Phantom
        Patient phantom.
    table : Phantom
        Table phantom.
    pad : Phantom
        Pad phantom.
    beam : Beam
        X-ray beam geometry.
    mode : str
        Plot mode label.
    patient_text : list[str]
        Hover text for the patient mesh.
    source_text : list[str]
        Hover text for the X-ray source.
    table_text : list[str]
        Hover text for the table mesh.
    detectors_text : list[str]
        Hover text for the detector mesh.
    pad_text : list[str]
        Hover text for the pad mesh.
    beam_text : list[str]
        Hover text for the beam mesh.
    title : str
        Plot title.
    dark_mode : bool, optional
        Use dark theme. Defaults to True.
    notebook_mode : bool, optional
        Optimize figure size for notebooks. Defaults to False.

    """

    logger.debug("Creating meshes for plot")

    patient_mesh = create_mesh_3d_general(
        obj=patient,
        color=COLOR_PATIENT,
        mesh_text=patient_text,
        lighting={"diffuse": PLOT_LIGHTNING_DIFFUSE, "ambient": PLOT_LIGHTNING_AMBIENT},
    )

    source_mesh = go.Scatter3d(
        x=[beam.r[0, 0], beam.r[0, 0]],
        y=[beam.r[0, 1], beam.r[0, 1]],
        z=[beam.r[0, 2], beam.r[0, 2]],
        hoverinfo="text",
        mode="markers",
        marker={"size": PLOT_SOURCE_SIZE, "color": COLOR_SOURCE},
        text=source_text,
    )

    table_mesh = create_mesh_3d_general(obj=table, color=COLOR_TABLE, mesh_text=table_text)

    detector_mesh = create_mesh_3d_general(obj=beam, color=COLOR_DETECTOR, mesh_text=detectors_text, detector_mesh=True)

    pad_mesh = create_mesh_3d_general(obj=pad, color=COLOR_PAD, mesh_text=pad_text, mesh_name=MESH_NAME_PAD)

    beam_mesh = create_mesh_3d_general(obj=beam, color=COLOR_BEAM, opacity=MESH_OPACITY_BEAM, mesh_text=beam_text)

    logger.debug("Create wireframes")
    wf_beam, wf_table, wf_pad, wf_detector = create_wireframes(
        beam=beam,
        table=table,
        pad=pad,
        line_width=PLOT_WIREFRAME_LINE_WIDTH,
        visible=True,
    )

    logger.debug("Setting up plot layout settings")
    layout = default_geometry_layout(
        title=title,
        dark_mode=dark_mode,
        notebook_mode=notebook_mode,
    )

    data = [
        patient_mesh,
        source_mesh,
        table_mesh,
        detector_mesh,
        pad_mesh,
        beam_mesh,
        wf_beam,
        wf_table,
        wf_pad,
        wf_detector,
    ]

    create_plot_and_save_to_file(mode=mode, data=data, layout=layout)
