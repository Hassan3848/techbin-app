"""
ML inference interface for TechBin.

Current stage:
    Mock inference implementation.

Future stage:
    Replace MockWasteClassifier with a real TFLite classifier while keeping
    the same InferenceResult output shape.

Purpose:
    The rest of the runtime should not care whether prediction comes from:
        - manual input
        - mock inference
        - real TensorFlow Lite model

    It should only receive:
        predicted_class
        confidence
        model_name
        inference_time_ms
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import settings
from app.engine.disposal_validator import validate_confidence
from app.logger import get_logger
from app.ml.labels import (
    VALID_WASTE_CLASSES,
    WasteLabelError,
    normalize_waste_class,
)


logger = get_logger(__name__)


class InferenceError(RuntimeError):
    """Raised when ML inference fails."""


@dataclass(frozen=True)
class InferenceResult:
    """
    Standard ML inference result.

    Attributes:
        predicted_class:
            One of TechBin's supported 6 waste classes.

        confidence:
            Model confidence score from 0.0 to 1.0.

        model_name:
            Name/version of model implementation.

        inference_time_ms:
            Runtime duration in milliseconds.

        image_path:
            Image used for inference.

        raw_output:
            Optional raw model/debug output.
    """

    predicted_class: str
    confidence: float
    model_name: str
    inference_time_ms: float
    image_path: str
    raw_output: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert result to a plain dictionary.
        """

        return asdict(self)


class WasteClassifier(Protocol):
    """
    Interface that all waste classifiers must follow.
    """

    model_name: str

    def predict(self, image_path: str | Path) -> InferenceResult:
        """
        Predict waste class from an image.
        """


def _normalize_image_path(image_path: str | Path) -> Path:
    """
    Normalize and validate image path before inference.
    """

    if isinstance(image_path, Path):
        path = image_path.expanduser().resolve()
    elif isinstance(image_path, str):
        if image_path.strip() == "":
            raise InferenceError("image_path cannot be empty")
        path = Path(image_path).expanduser().resolve()
    else:
        raise InferenceError(
            f"image_path must be str or Path, got {type(image_path).__name__}"
        )

    if not path.exists():
        raise InferenceError(f"Image file does not exist: {path}")

    if not path.is_file():
        raise InferenceError(f"Image path is not a file: {path}")

    if path.stat().st_size <= 0:
        raise InferenceError(f"Image file is empty: {path}")

    return path


class MockWasteClassifier:
    """
    Mock classifier for development before real model integration.

    Default behavior:
        Always returns the configured mock class and mock confidence.

    Optional random mode:
        Can randomly choose from the 6 supported classes for testing pipeline
        behavior across multiple labels.
    """

    model_name = "mock-waste-classifier-v1"

    def __init__(
        self,
        predicted_class: str | None = None,
        confidence: float | None = None,
        randomize: bool = False,
        random_seed: int | None = None,
    ) -> None:
        self.predicted_class = normalize_waste_class(
            predicted_class or settings.ml.mock_class
        )
        self.confidence = validate_confidence(
            settings.ml.mock_confidence if confidence is None else confidence
        )
        self.randomize = randomize
        self._random = random.Random(random_seed)

    def predict(self, image_path: str | Path) -> InferenceResult:
        """
        Return a mock prediction for a real image path.
        """

        path = _normalize_image_path(image_path)

        start_time = time.perf_counter()

        if self.randomize:
            predicted_class = self._random.choice(VALID_WASTE_CLASSES)
            confidence = round(self._random.uniform(0.70, 0.98), 4)
        else:
            predicted_class = self.predicted_class
            confidence = self.confidence

        try:
            normalized_class = normalize_waste_class(predicted_class)
            normalized_confidence = validate_confidence(confidence)
        except (WasteLabelError, ValueError) as exc:
            raise InferenceError("Mock classifier produced invalid output") from exc

        inference_time_ms = (time.perf_counter() - start_time) * 1000.0

        result = InferenceResult(
            predicted_class=normalized_class,
            confidence=normalized_confidence,
            model_name=self.model_name,
            inference_time_ms=round(inference_time_ms, 3),
            image_path=str(path),
            raw_output={
                "mode": "mock",
                "randomize": self.randomize,
            },
        )

        logger.info(
            "Mock inference completed | image=%s | class=%s | confidence=%.3f | time_ms=%.3f",
            path,
            result.predicted_class,
            result.confidence,
            result.inference_time_ms,
        )

        return result


class TFLiteWasteClassifier:
    """
    Placeholder for future real TensorFlow Lite inference.

    We are intentionally not implementing this yet because the real model file,
    preprocessing size, normalization rules, and label order must be finalized
    first.

    Later this class will:
        1. load .tflite model
        2. preprocess image
        3. run interpreter
        4. map output index to class label
        5. return InferenceResult
    """

    model_name = "tflite-waste-classifier"

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path).expanduser().resolve()

        if not self.model_path.exists():
            raise InferenceError(f"TFLite model file does not exist: {self.model_path}")

        raise NotImplementedError(
            "TFLiteWasteClassifier is planned for the real model integration phase."
        )

    def predict(self, image_path: str | Path) -> InferenceResult:
        raise NotImplementedError(
            "TFLiteWasteClassifier.predict() is not implemented yet."
        )


def create_mock_classifier(
    predicted_class: str | None = None,
    confidence: float | None = None,
    randomize: bool = False,
    random_seed: int | None = None,
) -> MockWasteClassifier:
    """
    Factory for mock classifier.
    """

    return MockWasteClassifier(
        predicted_class=predicted_class,
        confidence=confidence,
        randomize=randomize,
        random_seed=random_seed,
    )


def predict_image(
    image_path: str | Path,
    classifier: WasteClassifier | None = None,
) -> InferenceResult:
    """
    Predict image using provided classifier or default mock classifier.
    """

    active_classifier = classifier or create_mock_classifier()
    return active_classifier.predict(image_path)


__all__ = [
    "InferenceError",
    "InferenceResult",
    "WasteClassifier",
    "MockWasteClassifier",
    "TFLiteWasteClassifier",
    "create_mock_classifier",
    "predict_image",
]
