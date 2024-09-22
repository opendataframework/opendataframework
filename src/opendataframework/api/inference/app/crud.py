"""CRUD module."""

from typing import Any

import pandas as pd

from app.models import Entity


def predict(entity: Entity, inference: Any) -> float:
    """Predict."""
    data = pd.DataFrame(entity.dict(), index=[0])
    predictions = inference.predict(data)
    return predictions[0]
