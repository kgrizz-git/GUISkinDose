"""Table-translation direction multipliers.

Each attribute is +1 or -1 and is used as a multiplicative correction
factor to flip the sign of the corresponding translation direction.
"""


class TranslationDirection:
    """Switch pos/neg direction of table translations.

    Attributes
    ----------
    keys of __init__ parameter directions
        Value of each attribute (i.e. key) is integers of either +1 or -1 to be
        used as a multiplicative correction factor to switch pos/neg direction
        in each direction. PySkinDose default angles are all +1.

    """

    x: int
    y: int
    z: int

    def __init__(self, directions: dict[str, str] | None = None):
        """Initialize class attributes.

        Parameters
        ----------
        directions : dict
            dictionary with keys 'x', 'y' and 'z'.
            Each key contains either '+' or '-'.

        """
        self.x = 1 if directions is None else self._get_direction_as_value(directions["x"])
        self.y = 1 if directions is None else self._get_direction_as_value(directions["y"])
        self.z = 1 if directions is None else self._get_direction_as_value(directions["z"])

    def update_translation_direction(self, directions: dict[str, str]):
        """Update direction multipliers from a dict of '+'/'-'.

        Parameters
        ----------
        directions : dict[str, str]
            Mapping of x, y, z to '+' or '-'.

        """
        self.x = self._get_direction_as_value(directions["x"])
        self.y = self._get_direction_as_value(directions["y"])
        self.z = self._get_direction_as_value(directions["z"])

    @staticmethod
    def _get_direction_as_value(direction: str):
        if direction not in ("+", "-"):
            raise ValueError(f"The direction must be given as '+' or '-' but was given as {direction}")

        return 1 if direction == "+" else -1
