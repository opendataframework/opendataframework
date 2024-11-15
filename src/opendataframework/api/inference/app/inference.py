"""Inference module."""

import json
import os
import pickle
import uuid
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

MODELS_PATH = os.path.join(Path(__file__).parent, ".models")
PACKAGE_NAME = None
MODEL_NAME = None
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class Inference:
    """Inference class."""

    def __init__(
        self,
        uid: str = None,
        model_path: str = None,
        package_name: str = PACKAGE_NAME,
        model_name: str = MODEL_NAME,
        model: Any = None,
        config_path: str = None,
        config: Dict = None,
        *args,
        **kwargs: Dict,
    ) -> None:
        """Init method."""
        if uid:
            if not config_path:
                if os.path.exists(os.path.join(MODELS_PATH, uid, "model.json")):
                    config_path = os.path.join(MODELS_PATH, uid, "model.json")

            if not model_path:
                if os.path.exists(os.path.join(MODELS_PATH, uid, "model.pkl")):
                    model_path = os.path.join(MODELS_PATH, uid, "model.pkl")

        self._uid = uid or str(uuid.uuid4())
        self._model = None
        self._config = config or {
            "package": package_name,
            "model": model_name,
            "parameters": kwargs,
        }

        if not self._config.get("package"):
            self._config["package"] = package_name

        if not self._config.get("model"):
            self._config["model"] = model_name

        if model:
            self._model = model

        elif model_path:
            assert model_path.endswith(".pkl")
            with open(model_path, "rb") as file:
                self._model = pickle.load(file)  # nosec

        if config_path:
            assert config_path.endswith(".json")
            with open(config_path, "r") as file:
                self._config = json.load(file)

        if not self._model:
            assert self._config.get("package") and self._config.get("model")

            model_cls = getattr(
                __import__(self._config["package"], fromlist=[self._config["model"]]),
                self._config["model"],
            )

            self._model = model_cls(**self._config["parameters"])
            if self._config.get("fit"):
                self.fit(**self._config["fit"])
            self.save()

        assert hasattr(self._model, "fit")
        assert hasattr(self._model, "predict")

    @property
    def config(self):
        """Config."""
        return {
            "uid": self._uid,
            "package": self._config["package"],
            "model": self._config["model"],
            "parameters": self._config["parameters"],
            "is_fit": bool(self._config.get("fit")),
        }

    def fit(self, **kwargs) -> None:
        """Fits model."""
        self._model.fit(**self.prepare(**kwargs))
        self._config["fit"] = kwargs
        self.save()

    def predict(self, **kwargs) -> Any:
        """Makes prediction using configured model."""
        prediction = self._model.predict(**self.prepare(**kwargs))
        self._config["predict"] = kwargs

        if isinstance(prediction, pd.DataFrame):
            for col_name, col_type in prediction.dtypes.to_dict().items():
                if "datetime" in str(col_type):
                    prediction[col_name] = prediction[col_name].dt.strftime(DATE_FORMAT)
            prediction = prediction.replace(np.nan, None)
            self._config["prediction"] = prediction.to_dict("records")

        elif isinstance(prediction, pd.Series):
            prediction = prediction.replace(np.nan, None)
            self._config["prediction"] = prediction.tolist()

        elif isinstance(prediction, np.ndarray):
            prediction[np.isnan(prediction)] = None
            self._config["prediction"] = prediction.tolist()

        else:
            self._config["prediction"] = prediction

        self.save()

        return prediction

    @staticmethod
    def prepare(**kwargs):
        """Prepares kwargs before use by model.

        Converts each kwarg to pd.DataFrame where possible.
        """
        for key, value in kwargs.items():
            if isinstance(value, pd.DataFrame):
                continue
            try:
                kwargs[key] = pd.DataFrame.from_records(value)
            except TypeError:
                pass
        return kwargs

    def __str__(self):
        """String method."""
        return f"{self.__class__.__name__}: {self._model}"

    def save(self, path: str = MODELS_PATH):
        """Dumps model config to `model.json` & pickles model to `model.pkl`."""
        path = os.path.join(path, self._uid)

        os.makedirs(path, exist_ok=True)

        with open(os.path.join(path, "model.json"), "w") as f:
            json.dump(self._config, f, indent=2)

        with open(os.path.join(path, "model.pkl"), "wb") as f:
            pickle.dump(self._model, f, protocol=pickle.HIGHEST_PROTOCOL)
