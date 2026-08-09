import copy
from itertools import chain
from pathlib import Path

import numpy as np
import pandas as pd
from stl import mesh

from mypyskindose.phantom_mesh_names import resolve_human_mesh_stl_path
from mypyskindose.plotting.create_ploty_ijk_indices import (
    _create_plotly_ijk_indices_for_cuboid_objects,
)
from mypyskindose.settings.phantom_dimensions import PhantomDimensions

# valid phantom types
VALID_PHANTOM_MODELS = ["plane", "cylinder", "human", "table", "pad"]


def _validated_resolution(value: object, setting_name: str) -> str:
    """Return a supported phantom resolution or raise a user-facing error."""
    if not isinstance(value, str) or value.lower() not in {"dense", "sparse"}:
        raise ValueError(
            f"Unsupported {setting_name}: '{value}'. Allowed values are 'dense' or 'sparse'."
        )
    return value.lower()


class Phantom:
    """Create and handle phantoms for patient, support table and pad.

    This class creates a phantom of any of the types specified in
    VALID_PHANTOM_MODELS (plane, cylinder or human to represent the patient,
    as well as patient support table and pad). The patient phantoms consists of
    a number of skin cells where the skin dose can be calculated.

    Attributes
    ----------
    phantom_model : str
        Type of phantom, i.e. "plane", "cylinder", "human", "table" or "pad"
    r : np.ndarray
        n*3 array where n are the number of phantom skin cells. Each row
        contains the xyz coordinate of one of the phantom skin cells
    ijk : np.array
        A matrix containing vertex indices. This is required in order to
        plot the phantom using plotly Mesh3D. For more info, see "i", "j", and
        "k" at https://plot.ly/python/reference/#mesh3d
    dose : np.array
        An empty 1d array to store skin dose calculation for each of the n
        phantom cells. Only for patient phantom types (plane, cylinder, human)
    n : np.array
        normal vectors to each of the n phantom skin cells. (only for 3D
        patient phantoms, i.e. "cylinder" and "human")
    r_ref : np.array
        Empty array to store of reference position of the phantom cells after
        the phantom has been aligned in the geometry with the
        position_patient_phantom_on_table function in geom_calc.py
    table_length : float
        length of patient support table. The is needed for all phantom object
        to select correct rotation origin for At1, At2, and At3.


    """

    def __init__(
        self,
        phantom_model: str,
        phantom_dim: PhantomDimensions,
        human_mesh: str | tuple[str, mesh.Mesh | str | Path] | None = None,
        human_scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    ):
        """Create the phantom of choice.

        Parameters
        ----------
        phantom_model : str
            Type of phantom to create. Valid selections are 'plane',
            'cylinder', 'human', "table", and "pad".
        phantom_dim : PhantomDimensions
            instance of class PhantomDimensions containing dimensions for
            all phantoms models except human phantoms: Length, width, radius,
            thickness etc.
        human_mesh : str | tuple[str, mes.Mesh | temp_file], optional
            Choose which human mesh phantom to use. Valid selection are names
            of the *.stl-files in the phantom_data folder or a custom phantom
            sent in as either a mesh object or a svg given as a temp_file object
            (The default is none).

        Raises
        ------
        ValueError
            Raises value error if unsupported phantom type are selected,
            or if phantom_model='human' selected, without specifying
            human_mesh

        """
        self.phantom_model = phantom_model.lower()
        # Raise error if invalid phantom model selected
        if self.phantom_model not in VALID_PHANTOM_MODELS:
            raise ValueError(f"Unknown phantom model selected. Valid type: {'.'.join(VALID_PHANTOM_MODELS)}")

        self.human_model = None

        self.r_ref: np.ndarray

        # Save table length for all phantom in order to choose correct rotation
        # origin when applying At1, At2, and At3
        self.table_length = phantom_dim.table_length

        if self.phantom_model == "plane":
            self._init_plane(phantom_dim)
        elif self.phantom_model == "cylinder":
            self._init_cylinder(phantom_dim)
        elif self.phantom_model == "human":
            self._load_human_mesh(human_mesh, human_scale)
        elif self.phantom_model in ("table", "pad"):
            self._init_table_or_pad(self.phantom_model, phantom_dim)

    def _init_plane(self, phantom_dim: PhantomDimensions) -> None:
        """Create a plane phantom (2D rectangular grid); set self.r, self.ijk, self.dose."""
        # Resolution variables — set below depending on the plane_resolution setting.
        res_length: float
        res_width: float

        resolution = _validated_resolution(phantom_dim.plane_resolution, "plane_resolution")
        # Use a dense grid if specified by user
        if resolution == "dense":
            res_length = res_width = 2.0

        else:  # resolution == "sparse"; validated above
            res_length = res_width = 1.0

        # Linearly spaced points along the longitudinal direction
        x = np.linspace(
            -phantom_dim.plane_width / 2, +phantom_dim.plane_width / 2, int(res_width * phantom_dim.plane_width + 1)
        )
        # Linearly spaced points along the lateral direction
        z = np.linspace(0, -phantom_dim.plane_length, int(res_length * phantom_dim.plane_length))

        # Create phantom in form of rectangular grid
        x_plane, z_plane = np.meshgrid(x, z)

        # Create index vectors for plotly mesh3d plotting
        i2: list[int] = []
        i1 = j1 = k1 = i2

        for i in range(len(x) - 1):
            for j in range(len(z) - 1):
                i1 = [*i1, j * len(x) + i]
                j1 = [*j1, j * len(x) + i + 1]
                k1 = [*k1, j * len(x) + i + len(x)]
                i2 = [*i2, j * len(x) + i + len(x) + 1]

        self.r = np.column_stack((x_plane.ravel(), np.zeros(len(x_plane.ravel())), z_plane.ravel()))

        self.ijk = np.column_stack((i1 + i2, j1 + k1, k1 + j1))
        self.dose = np.zeros(len(self.r))

    def _init_cylinder(self, phantom_dim: PhantomDimensions) -> None:
        """Create an elliptic cylinder phantom; set self.r, self.ijk, self.dose, self.n."""
        # Resolution variables — set below depending on the cylinder_resolution setting.
        res_length: float
        res_width: float

        resolution = _validated_resolution(phantom_dim.cylinder_resolution, "cylinder_resolution")
        # Use a dense grid if specified by user
        if resolution == "dense":
            res_length = 4.0
            res_width = 0.05

        else:  # resolution == "sparse"; validated above
            res_length = 1.0
            res_width = 0.1

        # Creates linearly spaced points along an ellipse
        #  in the lateral direction
        t = np.arange(0 * np.pi, 2 * np.pi, res_width)
        x = (phantom_dim.cylinder_radii_a * np.cos(t)).tolist()
        y = (phantom_dim.cylinder_radii_b * np.sin(t)).tolist()

        # calculate normal vectors of a cylinder (pointing outwards)
        nx = np.cos(t) / (np.sqrt(np.square(np.cos(t) + 4 * np.square(np.sin(t)))))

        nz = np.zeros(len(t))

        ny = 2 * np.sin(t) / (np.sqrt(np.square(np.cos(t) + 4 * np.square(np.sin(t)))))

        nx = nx.tolist()
        ny = ny.tolist()
        nz = nz.tolist()

        n = [[nx[ind], ny[ind], nz[ind]] for ind in range(len(t))]

        # Store the  coordinates of the cylinder phantom, extended to span the entire length of the phantom, thus
        # creating an elliptical cylinder
        tmp_len = int(res_length) * (phantom_dim.cylinder_length + 2)
        output: dict = {
            "n": n * tmp_len,
            "x": x * tmp_len,
            "y": [el - phantom_dim.cylinder_radii_b for el in (y * tmp_len)],
            "z": list(chain(*[[-1 / res_length * ind] * len(x) for ind in range(tmp_len)])),
        }

        # Create index vectors for plotly mesh3d plotting
        i1 = list(range(len(output["x"]) - len(t)))
        j1 = list(range(1, len(output["x"]) - len(t) + 1))
        k1 = list(range(len(t), len(output["x"])))
        i2 = list(range(len(output["x"]) - len(t)))
        k2 = list(range(len(t) - 1, len(output["x"]) - 1))
        j2 = list(range(len(t), len(output["x"])))

        self.r = np.column_stack((output["x"], output["y"], output["z"]))
        self.ijk = np.column_stack((i1 + i2, j1 + j2, k1 + k2))
        self.dose = np.zeros(len(self.r))
        self.n = np.asarray(output["n"])

    def _load_human_mesh(
        self,
        human_mesh: str | tuple[str, mesh.Mesh | str | Path] | None,
        human_scale: tuple[float, float, float],
    ) -> None:
        """Load STL or tuple-supplied human mesh; set self.r, self.n, self.ijk, self.dose, self.human_model."""
        if human_mesh is None:
            raise ValueError('Human model needs to be specified for phantom_model = "human"')

        if isinstance(human_mesh, str):
            # Load a package phantom only. Stems are allow-listed basenames resolved
            # under phantom_data/ (rejects ../ and unknown meshes). Custom meshes use
            # the tuple form below, which is an intentional trusted-caller path.
            phantom_path = resolve_human_mesh_stl_path(human_mesh)
            self.human_model = phantom_path.stem
            phantom_mesh = mesh.Mesh.from_file(str(phantom_path))
        elif isinstance(human_mesh, tuple):
            self.human_model, phantom_mesh = self._get_phantom_mesh_from_tuple(human_mesh)
        else:
            raise ValueError("No human model specified while 'phantom_model' is 'human'")

        r = phantom_mesh.vectors
        n = phantom_mesh.normals

        self.r = np.asarray([el for el_list in r for el in el_list])
        self.n = np.asarray([x for pair in zip(n, n, n, strict=True) for x in pair])
        if len(self.r) == 0 or len(self.r) % 3:
            raise ValueError("Human mesh must contain a non-empty whole number of triangles.")
        self._apply_human_scale(human_scale)

        # Create index vectors for plotly mesh3d plotting
        self.ijk = np.column_stack(
            (np.arange(0, len(self.r), 3), np.arange(1, len(self.r), 3), np.arange(2, len(self.r), 3))
        )
        self.dose = np.zeros(len(self.r))

    def _init_table_or_pad(self, phantom_model: str, phantom_dim: PhantomDimensions) -> None:
        """Create cuboid vertices for the patient support table or pad; set self.r, self.ijk."""
        if phantom_model == "table":
            width = phantom_dim.table_width
            thickness = phantom_dim.table_thickness
            length = phantom_dim.table_length
            y_sign = +1
        else:  # "pad"
            width = phantom_dim.pad_width
            thickness = phantom_dim.pad_thickness
            length = phantom_dim.pad_length
            y_sign = -1

        # Physical lateral/across-table positions of the vertices.
        x = [index * width for index in [+0.5, +0.5, -0.5, -0.5, +0.5, +0.5, -0.5, -0.5]]

        # Vertical position of the vertices
        y = [index * thickness for index in [0, 0, 0, 0, y_sign, y_sign, y_sign, y_sign]]

        # Physical longitudinal/along-table positions of the vertices.
        z = [index * length for index in [0, -1, -1, 0, 0, -1, -1, 0]]

        # Create index vectors for plotly mesh3d plotting
        i, j, k = _create_plotly_ijk_indices_for_cuboid_objects()

        self.r = np.column_stack((x, y, z))
        self.ijk = np.column_stack((i, j, k))

    @staticmethod
    def _get_phantom_mesh_from_tuple(
        phantom_mesh_tuple: tuple[str, mesh.Mesh | str | Path]
    ) -> tuple[str, mesh.Mesh]:
        if not isinstance(phantom_mesh_tuple[0], str):
            raise TypeError(
                "If human_mesh is specified as a tuple, the first element must be the phantom name as a string"
            )

        if isinstance(phantom_mesh_tuple[1], mesh.Mesh):
            return phantom_mesh_tuple[0], phantom_mesh_tuple[1]

        return phantom_mesh_tuple[0], mesh.Mesh.from_file(str(phantom_mesh_tuple[1]))

    def _apply_human_scale(self, scale: tuple[float, float, float]) -> None:
        if np.allclose(scale, (1.0, 1.0, 1.0)):
            return

        scale_array = np.asarray(scale, dtype=float)
        anchor = np.array(
            [
                (self.r[:, 0].min() + self.r[:, 0].max()) / 2.0,
                self.r[:, 1].max(),
                self.r[:, 2].max(),
            ]
        )
        self.r = anchor + (self.r - anchor) * scale_array
        self._recompute_human_normals_from_triangles()

    def _recompute_human_normals_from_triangles(self) -> None:
        triangles = self.r.reshape(-1, 3, 3)
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        nonzero = lengths > 0
        normals[nonzero] = normals[nonzero] / lengths[nonzero, None]
        self.n = np.repeat(normals, 3, axis=0)

    def rotate(self, angles: list[int]) -> None:
        """Rotate the phantom about the angles specified in rotation.

        Parameters
        ----------
        angles: List[int]
            list of angles in degrees the phantom should be rotated about,
            given as [x_rot: <int>, y_rot: <int>, z_rot: <int>]. E.g.
            rotation = [0, 90, 0] will rotate the phantom 90 degrees about the
            y-axis.

        """
        # convert degrees to radians
        angles_rad = np.deg2rad(angles)

        x_rot = angles_rad[0]
        y_rot = angles_rad[1]
        z_rot = angles_rad[2]

        # Define rotation matricies about the x, y and z axis
        Rx = np.array([[+1, +0, +0], [+0, +np.cos(x_rot), -np.sin(x_rot)], [+0, +np.sin(x_rot), +np.cos(x_rot)]])
        Ry = np.array([[+np.cos(y_rot), +0, +np.sin(y_rot)], [+0, +1, +0], [-np.sin(y_rot), +0, +np.cos(y_rot)]])
        Rz = np.array([[+np.cos(z_rot), -np.sin(z_rot), +0], [+np.sin(z_rot), +np.cos(z_rot), +0], [+0, +0, +1]])

        # Rotate position vectors to the phantom cells

        self.r = np.matmul(Rx, np.matmul(Ry, np.matmul(Rz, self.r.T))).T

        if self.phantom_model in ["cylinder", "human"]:

            self.n = np.matmul(Rx, np.matmul(Ry, np.matmul(Rz, self.n.T))).T

    def translate(self, dr: list[float]) -> None:
        """Translate the phantom in the x, y or z direction.

        Parameters
        ----------
        dr : list[float]
            list of distances the phantom should be translated, given in cm.
            Specified as dr = [dx, dy, dz]. E.g.
            dr = [0, 0, 10] will translate the phantom 10 cm in the z direction

        """
        self.r[:, 0] += dr[0]
        self.r[:, 1] += dr[1]
        self.r[:, 2] += dr[2]

    def save_position(self) -> None:
        """Store a reference position of the phantom.

        This function is supposed to be used to store the patient fixation
        conducted in the function position_patient_phantom_on_table

        """
        r_ref = copy.copy(self.r)
        self.r_ref = r_ref

    def position(self, data_norm: pd.DataFrame, event: int) -> None:
        """Position the phantom for a event by adding RDSR table displacement.

        Positions the phantom from reference position to actual position
        according to the table displacement info in data_norm.

        Parameters
        ----------
        data_norm : pd.DataFrame
            Table containing dicom RDSR information from each irradiation event
            See rdsr_normalizer.py for more information.
        event : int
            Irradiation event index

        """
        self.r = copy.copy(self.r_ref)

        # displace phantom to table rotation center
        self.r[:, 2] += self.table_length / 2

        # Apply table rotation
        self.r = np.matmul(
            data_norm.Rz[event], np.matmul(data_norm.Ry[event], np.matmul(data_norm.Rx[event], self.r.T))
        ).T

        # Replace phantom back to starting position
        self.r[:, 2] -= self.table_length / 2

        # Apply phantom translation
        t = np.array([data_norm.Tx[event], data_norm.Ty[event], data_norm.Tz[event]])

        self.r = self.r + t
