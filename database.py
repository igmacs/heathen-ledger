import os
import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

# Base class for all database models
Base = declarative_base()

# Retrieve database configuration from environment
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    db_path = os.environ.get("DB_PATH", "data/ledger.db")
    database_url = f"sqlite:///{db_path}"

# For SQLite, ensure the parent directory exists
if database_url.startswith("sqlite:///"):
    db_file_path = database_url.replace("sqlite:///", "")
    if db_file_path:
        db_dir = os.path.dirname(db_file_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

# Configure sqlite engine to handle multithreading/async contexts safely
connect_args = {}
if database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(database_url, connect_args=connect_args)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database transaction error, rolled back: {e}")
        raise
    finally:
        session.close()


def init_db() -> None:
    """
    Initializes the database by creating all tables.
    Note: When using Alembic, tables are usually created/evolved via migrations.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
