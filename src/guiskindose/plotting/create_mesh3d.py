"""Create Plotly Mesh3d traces for phantoms, beams, and detectors."""

import plotly.graph_objects as go

from ..beam_class import Beam
from ..phantom_class import Phantom
from .get_visual_offset import _get_visual_offset


def create_mesh_3d_general(
    obj: Phantom | Beam,
    color: str,
    mesh_text: list[str],
    opacity: float | None = None,
    mesh_name: str | None = None,
    lighting: dict | None = None,
    detector_mesh: bool = False,
    visible_status: bool | None = True,
) -> go.Mesh3d:
    """Create a Plotly Mesh3d trace for a phantom or detector object.

    Parameters
    ----------
    obj : Phantom | Beam
        Geometry object to render.
    color : str
        Plotly color string or hex code.
    mesh_text : list[str]
        Hover text for each mesh vertex.
    opacity : float, optional
        Surface opacity in [0, 1]. Defaults to 1.0.
    mesh_name : str, optional
        Trace name shown in the legend.
    lighting : dict, optional
        Plotly lighting dict (e.g. ``{"diffuse": 0.5, "ambient": 0.5}``).
    detector_mesh : bool, optional
        Use the detector surface instead of the object surface. Defaults to False.
    visible_status : bool, optional
        Initial trace visibility. Defaults to True.

    Returns
    -------
    go.Mesh3d
        Configured Plotly mesh trace.

    """

    if opacity is None:
        opacity = 1.0

    visual_offset = _get_visual_offset(patient=obj)

    if detector_mesh:
        if not isinstance(obj, Beam):
            raise TypeError("detector_mesh requires a Beam instance")
        mesh_x = obj.det_r[:, 0]
        mesh_y = obj.det_r[:, 1] + visual_offset
        mesh_z = obj.det_r[:, 2]
        mesh_i = obj.det_ijk[:, 0]
        mesh_j = obj.det_ijk[:, 1]
        mesh_k = obj.det_ijk[:, 2]
    else:
        mesh_x = obj.r[:, 0]
        mesh_y = obj.r[:, 1] + visual_offset
        mesh_z = obj.r[:, 2]
        mesh_i = obj.ijk[:, 0]
        mesh_j = obj.ijk[:, 1]
        mesh_k = obj.ijk[:, 2]

    if lighting is None and mesh_name is None:
        return go.Mesh3d(
            x=mesh_x,
            y=mesh_y,
            z=mesh_z,
            i=mesh_i,
            j=mesh_j,
            k=mesh_k,
            color=color,
            hoverinfo="text",
            text=mesh_text,
            opacity=opacity,
            visible=visible_status,
        )

    if mesh_name is None:
        return go.Mesh3d(
            x=mesh_x,
            y=mesh_y,
            z=mesh_z,
            i=mesh_i,
            j=mesh_j,
            k=mesh_k,
            color=color,
            hoverinfo="text",
            text=mesh_text,
            opacity=opacity,
            lighting=lighting,
            visible=visible_status,
        )

    if lighting is None:
        return go.Mesh3d(
            x=mesh_x,
            y=mesh_y,
            z=mesh_z,
            i=mesh_i,
            j=mesh_j,
            k=mesh_k,
            color=color,
            hoverinfo="text",
            text=mesh_text,
            name=mesh_name,
            opacity=opacity,
            visible=visible_status,
        )

    return go.Mesh3d(
        x=mesh_x,
        y=mesh_y,
        z=mesh_z,
        i=mesh_i,
        j=mesh_j,
        k=mesh_k,
        color=color,
        hoverinfo="text",
        text=mesh_text,
        name=mesh_name,
        lighting=lighting,
        opacity=opacity,
        visible=visible_status,
    )
