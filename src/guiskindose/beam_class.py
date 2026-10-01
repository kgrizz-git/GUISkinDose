"""Provides the Beam class for modeling the X-ray source, beam geometry, and detector."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .phantom_class import Phantom


@dataclass(frozen=True)
class BeamGeometryInputs:
    """The per-event scalars a :class:`Beam` needs, independent of its angles.

    Every value here is constant across the candidate poses of one rotational
    event, so a coverage envelope reads them once instead of once per candidate
    (ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN, Phase 2). Frozen so a record cannot
    be mutated into something no beam was built for.

    Attributes
    ----------
    dsi : float
        Source-isocenter displacement (cm), applied along +y.
    dsd : float
        Source-detector distance (cm).
    fs_long : float
        Field size, longitudinal axis (cm), at the detector plane.
    fs_lat : float
        Field size, lateral axis (cm), at the detector plane.
    did : float
        Isocenter-detector distance (cm).
    dsl : float
        Detector side length (cm), i.e. both in-plane detector dimensions.
    """

    dsi: float
    dsd: float
    fs_long: float
    fs_lat: float
    did: float
    dsl: float

    @classmethod
    def from_frame(cls, data_norm: pd.DataFrame, event: int) -> "BeamGeometryInputs":
        """Read the scalars for one event out of the normalized event table.

        Parameters
        ----------
        data_norm : pd.DataFrame
            Dicom RDSR information from each irradiation event. See
            rdsr_normalizer.py for more information.
        event : int
            Index of the irradiation event in the procedure.

        Returns
        -------
        BeamGeometryInputs
            The event's beam scalars.

        Notes
        -----
        ``DSL`` is read at index ``0``, not at ``event`` — a pre-existing quirk
        of :class:`Beam` (detector side length is taken from the first event and
        reused for every later one). It is preserved here deliberately rather
        than "fixed": :class:`Beam` is constructed from many code paths, so
        changing which row supplies ``DSL`` would change numbers for every event
        after the first. Any change to that belongs in its own change with its
        own numbers discussion, not in a performance refactor.

        """
        return cls(
            dsi=float(data_norm.DSI[event]),
            dsd=float(data_norm.DSD[event]),
            fs_long=float(data_norm.FS_long[event]),
            fs_lat=float(data_norm.FS_lat[event]),
            did=float(data_norm.DID[event]),
            # Index [0], not [event] -- see the note above.
            dsl=float(data_norm.DSL[0]),
        )


class Beam:
    """A class used to create an X-ray beam and detector.

    Attributes
    ----------
    r : np.array
        5*3 array, locates the xyz coordinates of the apex and verticies of a
        pyramid shaped X-ray beam, where the apex represents the X-ray focus
        (row 1) and the vertices where the beam intercepts the X-ray detector
        (row 2-5)

    ijk : np.array
        A matrix containing vertex indices. This is required in order to
        plot the beam using plotly Mesh3D. For more info, see "i", "j", and "k"
        at https://plot.ly/python/reference/#mesh3d
    det_r: np.array
        8*3 array, where each row locates the xyz coordinate of one of the 8
        corners of the cuboid shaped X-ray detector
    det_ijk : np.array
        same as ijk, but for plotting the X-ray detector
    N : np.array
        4*3 array, where each row contains a normal vector to one of the four
        faces of the beam.
    """

    def __init__(self, data_norm: pd.DataFrame, event: int = 0, plot_setup: bool = False) -> None:
        """Initialize the beam and detector for a specific irradiation event.

        A thin adapter over :meth:`from_inputs`: it reads the event's scalars
        and angles out of ``data_norm`` and delegates. Callers that already hold
        a :class:`BeamGeometryInputs` should use :meth:`from_inputs` directly and
        skip the per-candidate DataFrame reads.

        Parameters
        ----------
        data_norm : pd.DataFrame
            Dicom RDSR information from each irradiation event. See
            rdsr_normalizer.py for more information.
        event : int, optional
            Specifies the index of the irradiation event in the procedure
            (the default is 0, which is the first event).
        plot_setup : bool, optional
            If True, the beam angulation info from data_norm is neglected,
            and a beam of zero angulation is created insted. This is a
            debugging feature used when positioning new phantoms or
            implementing currently unsupported venor RDSR files (the default is
            False).

        """
        inputs = BeamGeometryInputs.from_frame(data_norm=data_norm, event=event)
        # Override beam angulation if plot_setup
        if plot_setup:
            self._build(inputs=inputs, ap1_deg=0.0, ap2_deg=0.0, ap3_deg=0.0)
        else:
            self._build(
                inputs=inputs,
                # Fetch rotation angles of the X-ray tube
                ap1_deg=data_norm.Ap1[event],
                ap2_deg=data_norm.Ap2[event],
                ap3_deg=data_norm.Ap3[event],
            )

    @classmethod
    def from_inputs(cls, inputs: BeamGeometryInputs, ap1_deg: float, ap2_deg: float, ap3_deg: float) -> "Beam":
        """Build a beam from already-resolved scalars plus its three angles.

        The angles are passed in explicitly, in degrees, rather than read from
        an event table, so a caller evaluating many poses of one event (the
        rotational coverage envelope) resolves the scalars once and varies only
        the angles.

        Parameters
        ----------
        inputs : BeamGeometryInputs
            The event's beam scalars. These are not angles and are expected to
            be shared by every pose built from them.
        ap1_deg : float
            Positioner isocenter primary angle (Ap1), in degrees.
        ap2_deg : float
            Positioner isocenter secondary angle (Ap2), in degrees.
        ap3_deg : float
            Positioner isocenter detector rotation angle (Ap3), in degrees.

        Returns
        -------
        Beam
            The beam and detector for that pose.

        """
        beam = cls.__new__(cls)
        beam._build(inputs=inputs, ap1_deg=ap1_deg, ap2_deg=ap2_deg, ap3_deg=ap3_deg)
        return beam

    def _build(self, *, inputs: BeamGeometryInputs, ap1_deg: float, ap2_deg: float, ap3_deg: float) -> None:
        """Compute the beam and detector geometry for one pose.

        The shared body of both constructors: angles in degrees, scalars from a
        :class:`BeamGeometryInputs` record.
        """
        # Positioner isocenter primary angle (Ap1)
        # i.e. rotation of the X-ray beam and detector about the z axis.
        # Historical plot alias: LAT.
        ap1 = np.deg2rad(ap1_deg)
        # Positioner isocenter secondary angle (Ap2)
        # i.e. rotation of the X-ray beam and detector about the x axis.
        # Historical plot alias: LON.
        ap2 = np.deg2rad(ap2_deg)
        # Positioner isocenter detector rotation angle (Ap3)
        # i.e. rotation of the X-ray detector about the y axis (VERT)
        ap3 = np.deg2rad(ap3_deg)

        # calculate rotation about x axis
        angle = ap2
        Rx = np.array(
            [
                [+1, +0, +0],
                [+0, +np.cos(angle), -np.sin(angle)],
                [+0, +np.sin(angle), +np.cos(angle)],
            ]
        )

        # calculate rotation about y axis
        angle = ap3
        Ry = np.array(
            [
                [+np.cos(angle), +0, +np.sin(angle)],
                [+0, +1, +0],
                [-np.sin(angle), +0, +np.cos(angle)],
            ]
        )

        # calculate rotation about z axis
        angle = ap1
        Rz = np.array(
            [
                [+np.cos(angle), -np.sin(angle), +0],
                [+np.sin(angle), +np.cos(angle), +0],
                [+0, +0, +1],
            ]
        )

        # calculate source-isocenter displacement at ap1 = ap2 = 0
        delta_r = np.array([0, inputs.dsi, 0])

        # Create unit-beam in the positioner coordinate system
        r = np.array(
            [
                [0, 0, 0],  # r0 (i.e. X-ray source)
                [+0.5, -1.0, +0.5],  # r+
                [+0.5, -1.0, -0.5],  # r+-
                [-0.5, -1.0, -0.5],  # r-
                [-0.5, -1.0, +0.5],  # r-+
            ]
        )
        r[1:, 1] *= inputs.dsd
        # Field-size names follow the historical PySkinDose/DICOM-derived
        # aliases; see dev-docs/VENDOR_COORDINATE_SYSTEMS.md before relabeling.
        r[1:, 0] *= inputs.fs_long
        r[1:, 2] *= inputs.fs_lat

        # Transform the beam from the positioner coordinate system to the
        # isocenter coordinate system. Note! The transpose operations are
        # needed to broadcast over all vectors in r
        r = np.matmul(Rz, np.matmul(Rx, (r + delta_r).T)).T

        self.r = r

        # Manually create vertex index vector for the X-ray beam
        self.ijk = np.column_stack(([0, 0, 0, 0, 1, 1], [1, 1, 3, 3, 2, 3], [2, 4, 2, 4, 3, 4]))

        # Create unit vectors from X-ray source to beam verticies
        v = ((self.r[1:] - self.r[0, :]).T / np.linalg.norm(self.r[1:] - self.r[0, :], axis=1)).T

        # Create the four normal vectors to the faces of the beam.
        self.N = np.vstack(
            [
                np.cross(v[0, :], v[1, :]),
                np.cross(v[1, :], v[2, :]),
                np.cross(v[2, :], v[3, :]),
                np.cross(v[3, :], v[0, :]),
            ]
        )

        # Create detector corners for with side length 1
        # The first four rows represent the X-ray detector surface, the last
        # four are there to give the detector some depth for 3D visualization.
        det_r = np.array(
            [
                [+0.5, -1.0, +0.5],
                [+0.5, -1.0, -0.5],
                [-0.5, -1.0, -0.5],
                [-0.5, -1.0, +0.5],
                [+0.5, -1.2, +0.5],
                [+0.5, -1.2, -0.5],
                [-0.5, -1.2, -0.5],
                [-0.5, -1.2, +0.5],
            ]
        )

        # Add detector dimensions
        detector_width = inputs.dsl
        det_r[:, 0] *= detector_width
        det_r[:, 2] *= detector_width
        # Place detector at actual distance
        det_r[:, 1] *= inputs.did

        # Transform the detector from the positioner coordinate system to
        # the isocenter coordinate system. Note! The transpose operations
        # are needed to broadcast over all vector in r_det
        det_r = np.matmul(Rz, np.matmul(Ry, np.matmul(Rx, det_r.T))).T

        self.det_r = det_r

        # Manually construct vertex index vector for the X-ray detector
        self.det_ijk = np.column_stack(
            (
                [0, 0, 4, 4, 0, 1, 0, 3, 3, 7, 1, 1],
                [1, 2, 5, 6, 1, 5, 3, 7, 2, 2, 2, 6],
                [2, 3, 6, 7, 4, 4, 4, 4, 7, 6, 6, 5],
            )
        )

    def check_hit_mask(self, patient: Phantom) -> np.ndarray:
        """Calculate which patient entrance skin cells are hit by the beam, as an array.

        This is the array form of :meth:`check_hit` and is **internal**: the public
        surface of this class stays :meth:`check_hit`, so do not export
        ``check_hit_mask`` from ``guiskindose/__init__.py``.

        A description of this algorithm is presented in the wiki, please visit
        https://guiskindose.readthedocs.io/en/latest/

        Parameters
        ----------
        patient : Phantom
            Patient phantom, either of type plane, cylinder or human, i.e.
            instance of class Phantom

        Returns
        -------
        np.ndarray
            A boolean array of the same length as the number of patient skin
            cells. True for all entrance skin cells that are hit by the beam.

        """
        # Create vectors from X-ray source to each phantom skin cell
        v = patient.r - self.r[0, :]

        # Check which skin cells lies within the beam
        hits = (np.dot(v, self.N.T) <= 0).all(axis=1)
        # if patient phantom is 3D, remove exit path skin cells
        if patient.phantom_model != "plane":
            temp1 = v[hits]
            temp2 = patient.n[hits]

            # Vectorized form of ``[np.dot(a, b) <= 0 for a, b in zip(temp1, temp2)]``.
            # Equivalent up to floating point, NOT bit-identical: ``np.dot`` on a 1-D float64
            # pair dispatches to BLAS ``ddot``, while ``einsum`` uses numpy's own kernels with a
            # different summation order, so a row dot can differ in the last ulp (measured: ~34%
            # of 500k random 3-vector pairs differ bitwise, max abs diff 1.819e-12). Only the sign
            # feeds ``<= 0``, and a flip then needs the true dot within an ulp of zero: 0 of 500k
            # trials flipped, PR CI's closest binding sits ~1.7e-6 from zero (~9.3e5x that ceiling),
            # and the committed goldens (static Siemens cylinder, rotational envelope) pass with
            # this line — exactly on the generating platform, rtol=1e-12-bounded elsewhere (the
            # dose chain's own BLAS drifts ~1e-15 cross-platform regardless of this line; see
            # ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN 4.2). If a platform's golden goes red on this
            # edit and nothing else, this line is the suspect, and it is independently
            # revertible. Full analysis: ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN 1d.
            hits[hits] = np.einsum("ij,ij->i", temp1, temp2) <= 0

        return hits

    def check_hit(self, patient: Phantom) -> list[bool]:
        """Calculate which patient entrance skin cells are hit by the beam.

        A description of this algorithm is presented in the wiki, please visit
        https://guiskindose.readthedocs.io/en/latest/

        Parameters
        ----------
        patient : Phantom
            Patient phantom, either of type plane, cylinder or human, i.e.
            instance of class Phantom

        Returns
        -------
        list[bool]
            A boolean list of the same length as the number of patient skin
            cells. True for all entrance skin cells that are hit by the beam.

        """
        # The comprehension form, not list(...) and not .tolist(): list() over an
        # ndarray yields np.bool_ elements, which are not real bools and are not
        # JSON serializable, and newer numpy stubs type tolist() as unassignable
        # to list[bool] under basedpyright.
        return [bool(hit) for hit in self.check_hit_mask(patient=patient)]
