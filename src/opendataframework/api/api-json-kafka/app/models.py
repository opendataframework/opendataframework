"""Models module."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class HealthCheck(BaseModel):
    """Health check model."""

    name: str
    version: str
    description: str


class Entity(BaseModel):
    """Entity model."""

    # required fields
    uid: Optional[str] = Field(
        primary_key=True, index=True, default_factory=lambda: str(uuid4())
    )
    ts: datetime = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )

    # extra fields
