"""Router module."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.crud import predict
from app.dependencies import get_inference
from app.models import Entity

inference_router = APIRouter(prefix="/inference", tags=["inference"])


@inference_router.post("/", status_code=status.HTTP_200_OK)
def get_prediction(entity: Entity, inference: Any = Depends(get_inference)) -> float:
    """Create prediction."""
    prediction = predict(entity, inference)
    return prediction
