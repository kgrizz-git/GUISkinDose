"""Default Plotly camera configuration for geometry plots."""


def get_camera_view() -> dict[str, dict[str, float]]:
    """Return the default Plotly camera view for geometry plots.

    Returns
    -------
    dict[str, dict[str, float]]
        Camera configuration with ``up``, ``center`` and ``eye`` vectors.

    """
    return {
        "up": {"x": 0, "y": -1, "z": 0},
        "center": {"x": 0, "y": 0, "z": 0},
        "eye": {"x": -1.3, "y": -1.3, "z": 0.7},
    }
