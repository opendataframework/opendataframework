"""Models module."""

from pydantic import BaseModel
from sqlmodel import SQLModel


class HealthCheck(BaseModel):
    """Health check model."""

    name: str
    version: str
    description: str


class Entity(SQLModel):
    """Entity model."""

    __tablename__ = "entities"

    # extra fields
