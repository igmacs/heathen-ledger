import os
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("DB_PATH", "data/ledger.db")
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """
        Establishes and returns a connection to the SQLite database.
        Uses sqlite3.Row to allow dict-like access to rows.
        """
        if self._connection is None:
            try:
                # Ensure the database directory exists
                db_dir = os.path.dirname(self.db_path)
                if db_dir:
                    os.makedirs(db_dir, exist_ok=True)

                self._connection = sqlite3.connect(self.db_path)
                self._connection.row_factory = sqlite3.Row
                logger.info(f"Connected to SQLite database at {self.db_path}")
            except sqlite3.Error as e:
                logger.error(f"Failed to connect to database: {e}")
                raise
        return self._connection

    def close(self) -> None:
        """Closes the connection to the database if it exists."""
        if self._connection:
            try:
                self._connection.close()
                logger.info("Database connection closed.")
            except sqlite3.Error as e:
                logger.error(f"Failed to close database connection: {e}")
            finally:
                self._connection = None

    def __enter__(self):
        """Allows use of the Database class as a context manager."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the connection is closed when exiting the context manager."""
        self.close()

    def init_db(self) -> None:
        """
        Initializes the database.
        Schemas and initial tables will be defined here later.
        """
        conn = self.connect()
        try:
            # TODO: Define and execute schema creation statements here

            conn.commit()
            logger.info("Database initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            conn.rollback()
            raise
