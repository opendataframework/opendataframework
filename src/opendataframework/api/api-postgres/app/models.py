"""Models module."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel
from sqlmodel import Column, DateTime, Field, SQLModel


class HealthCheck(BaseModel):
    """Health check model."""

    name: str
    version: str
    description: str


class Entity(SQLModel, table=True):
    """Entity model."""

    __tablename__ = "entities"
    # required fields
    uid: Optional[str] = Field(
        primary_key=True, index=True, default_factory=lambda: str(uuid4())
    )
    ts: datetime = Field(
        sa_column=Column("__time", DateTime),
        default_factory=lambda: datetime.now().isoformat(),
    )

    # extra fields
