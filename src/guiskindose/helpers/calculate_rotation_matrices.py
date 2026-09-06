"""Compute C-arm rotation matrices from normalized RDSR angles.

Takes a DataFrame with At1/At2/At3 columns and appends Rx, Ry, Rz
matrix tuples as new columns.
"""
import numpy as np
import pandas as pd


def calculate_rotation_matrices(normalized_data: pd.DataFrame) -> pd.DataFrame:
    """Append Rx, Ry, Rz rotation matrices for each RDSR event.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        DataFrame containing normalized RDSR event data with At1, At2, At3
        angle columns.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with Rx, Ry, Rz columns added, each containing a
        3x3 rotation matrix.

    """
    angles = np.deg2rad(normalized_data.loc[:, ["At1", "At2", "At3"]].to_numpy(dtype=float))
    matrices = []
    for at1, at2, at3 in angles:
        matrices.append(
            (
                [
                    [+1, +0, +0],
                    [+0, +float(np.cos(at2)), -float(np.sin(at2))],
                    [+0, +float(np.sin(at2)), +float(np.cos(at2))],
                ],
                [
                    [+float(np.cos(at1)), +0, +float(np.sin(at1))],
                    [+0, +1, +0],
                    [-float(np.sin(at1)), +0, +float(np.cos(at1))],
                ],
                [
                    [+float(np.cos(at3)), -float(np.sin(at3)), +0],
                    [+float(np.sin(at3)), +float(np.cos(at3)), +0],
                    [+0, +0, +1],
                ],
            )
        )

    return normalized_data.join(
        pd.DataFrame(
            matrices,
            columns=["Rx", "Ry", "Rz"],
            index=normalized_data.index,
        )
    )
