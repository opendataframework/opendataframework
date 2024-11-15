"""Router module."""

import os
from io import BytesIO, StringIO
from typing import Dict, List

import pandas as pd
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.inference import MODELS_PATH, Inference
from app.models import Fit, Parameters, Predict, Prediction

inference_router = APIRouter(prefix="/inference", tags=["inference"])


@inference_router.get("/models", status_code=status.HTTP_200_OK)
def get_models() -> List:
    """GET list of models uuid."""
    result = []

    for name in os.listdir(MODELS_PATH):
        if not os.path.isdir(os.path.join(MODELS_PATH, name)):
            continue
        result.append(name)

    return result


@inference_router.get("/model/{model_id}", status_code=status.HTTP_200_OK)
def get_model(model_id: str) -> Dict:
    """GET model's parameters."""
    path = os.path.join(MODELS_PATH, model_id)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="model not found"
        )
    inference = Inference(uid=model_id)
    return inference.config


@inference_router.post("/model", status_code=status.HTTP_201_CREATED)
def init(parameters: Parameters) -> Dict:
    """Init model."""
    inference = Inference(**parameters.dict())
    inference.save()
    return inference.config


@inference_router.post("/model/{model_id}/fit", status_code=status.HTTP_201_CREATED)
def fit(model_id: str, fit: Fit) -> Dict:
    """Fit model."""
    path = os.path.join(MODELS_PATH, model_id)

    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="model not found"
        )

    inference = Inference(uid=model_id)
    inference.fit(**fit.dict())
    return inference.config


@inference_router.post(
    "/model/{model_id}/predict/", status_code=status.HTTP_201_CREATED
)
def predict(model_id: str, predict: Predict) -> Prediction:
    """Predict."""
    path = os.path.join(MODELS_PATH, model_id)

    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="model not found"
        )

    inference = Inference(uid=model_id)
    inference.predict(**predict.dict())

    prediction = Prediction(value=inference._config["prediction"])

    return prediction


@inference_router.post(
    "/model/{model_id}/predict/csv", status_code=status.HTTP_201_CREATED
)
def predict_csv(model_id: str, predict: Predict) -> StreamingResponse:
    """Prediction as csv file."""
    path = os.path.join(MODELS_PATH, model_id)

    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="model not found"
        )

    inference = Inference(uid=model_id)
    prediction = inference.predict(**predict.dict())

    if isinstance(prediction, pd.DataFrame):
        pass

    elif isinstance(prediction, pd.Series):
        prediction = prediction.to_frame()

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"csv format is not supported for model: {model_id}",
        )

    csv_file = StringIO()
    prediction.to_csv(csv_file, index=False)
    filename = f"{model_id}.csv"
    return StreamingResponse(
        BytesIO(csv_file.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@inference_router.get("/model/{model_id}/predict/csv", status_code=status.HTTP_200_OK)
def get_predict_csv(model_id: str) -> StreamingResponse:
    """Prediction as csv file."""
    path = os.path.join(MODELS_PATH, model_id)

    if not os.path.exists(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="model not found"
        )

    inference = Inference(uid=model_id)
    prediction = inference._config.get("prediction")

    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="prediction not found"
        )

    prediction = pd.DataFrame.from_records(prediction)  # TODO: handle properly

    csv_file = StringIO()
    prediction.to_csv(csv_file, index=False)
    filename = f"{model_id}_prediction.csv"
    return StreamingResponse(
        BytesIO(csv_file.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
