"""Dependencies module."""

import os
import pickle
from pathlib import Path

MODEL_PATH = os.path.join(Path(__file__).parent, "model.pkl")
INFERENCE_MODEL = None


def get_inference():
    """Get inference model."""
    global INFERENCE_MODEL

    if INFERENCE_MODEL is None:
        with open(MODEL_PATH, "rb") as file:
            INFERENCE_MODEL = pickle.load(file)  # nosec

    yield INFERENCE_MODEL
