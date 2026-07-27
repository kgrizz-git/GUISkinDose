from typing import Dict


def get_camera_view() -> Dict[str, Dict[str, float]]:
    return {
        "up": {"x": 0, "y": -1, "z": 0},
        "center": {"x": 0, "y": 0, "z": 0},
        "eye": {"x": -1.3, "y": -1.3, "z": 0.7},
    }
