"""Machine-origin translation offsets.

Specifies the offset in cm between the RDSR-generating unit's origin and
the GUISkinDose machine origin (x,y,z = 0,0,0).
"""


class TranslationOffset:
    """Set translation offset of patient support table.

    Use this class to set the translation offset (in cm) between the machine
    origin (the unit that generated the RDSR) and the machine origin of
    PySkinDose (which is located at (x,y,z) = (0, 0, 0)).

    Attributes
    ----------
    keys of __init__ parameter offset
        Value of each attribute (i.e. key) is a float specifying the offset
        in cm.

    """

    def __init__(self, offset: dict[str, float] | None = None):
        """Initialize class attributes.

        Parameters
        ----------
        offset : dict
            dictionary with keys 'x', 'y' and 'z'. Each key contains the
            translation offset (in that direction), specified as a float in cm.

        """
        if offset is None:
            offset = {}

        self.x: float = float(offset.get("x", 0.0) or 0.0)
        self.y: float = float(offset.get("y", 0.0) or 0.0)
        self.z: float = float(offset.get("z", 0.0) or 0.0)

    def update_translation_offset(self, offset: dict[str, float]):
        """Update translation offsets from a dict of floats.

        Parameters
        ----------
        offset : dict[str, float]
            Mapping of x, y, z to translation offsets in cm.

        """
        self.x = float(offset["x"])
        self.y = float(offset["y"])
        self.z = float(offset["z"])
