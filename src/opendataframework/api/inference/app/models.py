"""Models module."""

from datetime import datetime  # noqa: F401

from pydantic import BaseModel
from sqlmodel import SQLModel


class HealthCheck(BaseModel):
    """Health check model."""

    name: str
    version: str
    description: str


class Parameters(SQLModel):
    """Parameters model."""

    # parameters fields


class Fit(SQLModel):
    """Fit model."""

    # fit fields


class Predict(SQLModel):
    """Predict model."""

    # predict fields


class Prediction(SQLModel):
    """Prediction model."""

    # prediction fields
