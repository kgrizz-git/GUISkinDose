import numpy as np
import pandas as pd


def calculate_rotation_matrices(normalized_data: pd.DataFrame) -> pd.DataFrame:
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
