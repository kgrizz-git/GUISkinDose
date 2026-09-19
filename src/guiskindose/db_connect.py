"""SQLite database access for explicit legacy correction-factor databases.

Read-only: unlike the historical bootstrap behavior (which created and
populated a database in the working directory), this function never creates
files. Default correction lookup uses the packaged CSV provider
(:mod:`guiskindose.correction_data`) and never touches this module.
"""

import logging
import sqlite3
from pathlib import Path

from guiskindose.privacy import safe_error_event

logger = logging.getLogger("guiskindose")


def db_connect(db_name: str):
    """Open a read-only connection to an explicit correction-factor database.

    Parameters
    ----------
    db_name : str
        The path to an existing sqlite3 database. The file must exist; nothing
        is created or bootstrapped (use the packaged provider for default
        operation).

    Returns
    -------
    conn
        read-only connection to database
    cursor
        cursor to database connection

    """
    # Read-only URI: never create the file, and keep Windows paths intact.
    uri = f"{Path(db_name).resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)

        # Create cursor (enables sql commands using the sql method)
        cursor = conn.cursor()
    except sqlite3.Error as exc:
        safe_error_event(logger, "corrections_database_connect", exc)
        raise

    return conn, cursor
