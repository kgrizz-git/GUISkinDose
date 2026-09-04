from base_dev_settings import DEVELOPMENT_PARAMETERS

from guiskindose import constants
from guiskindose.main import main
from guiskindose.settings import PyskindoseSettings

settings = PyskindoseSettings(settings=DEVELOPMENT_PARAMETERS)
settings.mode = constants.MODE_PLOT_PROCEDURE

settings.rdsr_filename = "table_rotations.json"

main(settings=settings)
