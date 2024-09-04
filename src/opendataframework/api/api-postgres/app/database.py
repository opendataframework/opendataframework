"""Database module."""

from sqlmodel import SQLModel, create_engine

from app import settings

engine = create_engine(settings.db_connection_str, echo=True)


def init_db():
    """Init db."""
    SQLModel.metadata.create_all(engine)
