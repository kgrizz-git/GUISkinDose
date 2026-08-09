"""Table-origin coordinate conversion helpers shared by GUI modules."""

from __future__ import annotations

_TABLE_ORIGIN_AXES = ("x", "y", "z")


def _origin_source_to_final(meta: dict, origin: dict) -> dict[str, float]:
    """Map stored GUI transform-source table-origin values to final plotted axes."""
    source = {key: float(origin.get(key, 0.0)) for key in _TABLE_ORIGIN_AXES}
    if meta.get("swap_lat_lon", False):
        source["x"], source["z"] = source["z"], source["x"]
    return source


def _final_axis_to_source_axis(meta: dict, axis: str) -> str:
    """Return the stored-source axis corresponding to a final plotted axis."""
    if axis not in _TABLE_ORIGIN_AXES:
        raise KeyError(f"Unknown table-origin axis {axis!r}")
    if meta.get("swap_lat_lon", False) and axis in ("x", "z"):
        return "z" if axis == "x" else "x"
    return axis


def _table_origin_source_values(meta: dict) -> dict[str, float]:
    """Return override values when present, otherwise detected source-frame values."""
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    override = meta.get("table_origin_override")
    if override is not None:
        return {key: float(override.get(key, detected.get(key, 0.0))) for key in _TABLE_ORIGIN_AXES}
    return {key: float(detected.get(key, 0.0)) for key in _TABLE_ORIGIN_AXES}


def detected_table_origin(meta: dict) -> dict[str, float]:
    """Return the auto-detected table origin in final plotted-frame axes."""
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    return _origin_source_to_final(meta, detected)


def effective_table_origin(meta: dict) -> dict[str, float]:
    """Return the active table origin in final plotted-frame axes."""
    return _origin_source_to_final(meta, _table_origin_source_values(meta))


def stage_table_origin_axis(meta: dict, axis: str, value: float) -> None:
    """Update one final-frame table-origin axis without rebuilding event data."""
    source_axis = _final_axis_to_source_axis(meta, axis)
    numeric_value = float(value)
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    if meta.get("table_origin_override") is None:
        meta["table_origin_override"] = dict(detected)
    meta["table_origin_override"][source_axis] = numeric_value
