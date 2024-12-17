"""Database module."""

from sqlmodel import create_engine

from app import settings

engine = create_engine(settings.db_connection_str)
