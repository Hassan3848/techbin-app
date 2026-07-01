"""
Reusable EfficientNetV2 camera inference for the real TechBin Pi runtime.

This module preserves the preprocessing proven in
scripts/test_real_camera_ai_hardware_flow.py:
    - Picamera2 RGB888 preview frames
    - red/blue channel correction
    - model-package preprocessing_config.json
    - five-frame probability averaging
    - confidence and top-2 margin validation
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings


REAL_MODEL_CATEGORIES = ("cardboard", "paper", "plastic_glass", "metal", "trash")
RECYCLABLE_CATEGORIES = ("cardboard", "paper", "plastic_glass", "metal")
NON_RECYCLABLE_CATEGORIES = ("trash",)

DEFAULT_MODEL_FILE_NAME = "techbin_effnetv2_camera_dynamic_range.tflite"
DEFAULT_LABELS_FILE_NAME = "labels.json"
DEFAULT_CONFIG_FILE_NAME = "preprocessing_config.json"


class RealModelError(RuntimeError):
    """Raised when real camera/model inference cannot run."""


@dataclass(frozen=True)
class RealModelPackage:
    package_path: Path
    model_path: Path
    labels_path: Path
    config_path: Path
    model_version: str


@dataclass(frozen=True)
class RealPredictionResult:
    category: str
    label: str
    confidence: float
    margin: float
    accepted: bool
    rejectionReason: str | None
    expectedSide: str
    recyclable: bool
    modelVersion: str
    classificationSource: str
    inferenceBackend: str
    inferenceTimeMs: float
    imagePath: str
    top3: list[dict[str, Any]]
    rawOutput: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RealModelError("numpy is required for real model inference") from exc

    return np


def _load_pil_image():
    try:
        from PIL import Image
    except ImportError as exc:
        raise RealModelError("Pillow is required for real model inference") from exc

    return Image


def load_interpreter(model_path: Path):
    try:
        from ai_edge_litert.interpreter import Interpreter

        return Interpreter(model_path=str(model_path)), "ai_edge_litert"
    except Exception:
        pass

    try:
        from tflite_runtime.interpreter import Interpreter

        return Interpreter(model_path=str(model_path)), "tflite_runtime"
    except Exception:
        pass

    try:
        import tensorflow as tf

        return tf.lite.Interpreter(model_path=str(model_path)), "tensorflow.lite"
    except Exception as exc:
        raise RealModelError(
            "No LiteRT/TFLite interpreter is available in this environment."
        ) from exc


def load_labels(path: Path) -> dict[int, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RealModelError(f"Failed to read labels file: {path}") from exc

    if isinstance(data, list):
        labels = {index: str(label) for index, label in enumerate(data)}
    elif isinstance(data, dict):
        labels = {int(index): str(label) for index, label in data.items()}
    else:
        raise RealModelError("labels.json must contain a list or dictionary.")

    unknown = sorted(set(labels.values()) - set(REAL_MODEL_CATEGORIES))
    if unknown:
        raise RealModelError(
            "Model labels include unsupported categories: " + ", ".join(unknown)
        )

    return labels


def load_model_package(
    package_path: str | Path | None = None,
    *,
    model_version: str | None = None,
) -> RealModelPackage:
    raw_package = package_path or settings.ml.model_package_path
    if raw_package is None or str(raw_package).strip() == "":
        raise RealModelError("TECHBIN_MODEL_PACKAGE_PATH is required")

    package = Path(raw_package).expanduser().resolve()
    result = RealModelPackage(
        package_path=package,
        model_path=package / DEFAULT_MODEL_FILE_NAME,
        labels_path=package / DEFAULT_LABELS_FILE_NAME,
        config_path=package / DEFAULT_CONFIG_FILE_NAME,
        model_version=model_version or settings.ml.model_version,
    )

    for required_path in (result.model_path, result.labels_path, result.config_path):
        if not required_path.exists():
            raise RealModelError(f"Required model package file missing: {required_path}")

    return result


def softmax_if_needed(values: Any) -> Any:
    np = _load_numpy()
    values = np.asarray(values, dtype=np.float32)

    total = float(np.sum(values))
    if np.min(values) < -0.01 or np.max(values) > 1.2 or abs(total - 1.0) > 0.25:
        values = values - np.max(values)
        exponentials = np.exp(values)
        values = exponentials / np.sum(exponentials)

    return values


def preprocess_frame(frame_rgb: Any, image_size: list[int], input_dtype: Any) -> Any:
    np = _load_numpy()
    Image = _load_pil_image()

    image = Image.fromarray(frame_rgb).convert("RGB")
    image = image.resize((image_size[0], image_size[1]), Image.BILINEAR)
    array = np.asarray(image, dtype=np.float32)

    # EfficientNetV2 has preprocessing inside the model.
    # Feed RGB float32 values in the range 0..255.
    if input_dtype == np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    else:
        array = array.astype(input_dtype)

    return array[None, ...]


def predict_probabilities(
    interpreter: Any,
    input_details: list[dict[str, Any]],
    output_details: list[dict[str, Any]],
    frame_rgb: Any,
    image_size: list[int],
) -> Any:
    input_tensor = preprocess_frame(
        frame_rgb=frame_rgb,
        image_size=image_size,
        input_dtype=input_details[0]["dtype"],
    )

    interpreter.set_tensor(input_details[0]["index"], input_tensor)
    interpreter.invoke()

    output = interpreter.get_tensor(output_details[0]["index"])[0]
    scale, zero_point = output_details[0].get("quantization", (0.0, 0))
    if scale and scale > 0:
        np = _load_numpy()
        output = scale * (output.astype(np.float32) - zero_point)

    return softmax_if_needed(output)


def capture_corrected_rgb_frame(camera: Any) -> Any:
    frame = camera.capture_array()

    if frame.ndim != 3 or frame.shape[2] < 3:
        raise RealModelError(f"Unexpected camera frame shape: {frame.shape}")

    frame = frame[:, :, :3]
    return frame[:, :, [2, 1, 0]]


class EfficientNetV2CameraClassifier:
    """
    Real Pi Camera + EfficientNetV2 classifier.
    """

    def __init__(
        self,
        package: RealModelPackage | None = None,
        *,
        average_frames: int = 5,
        frame_interval_seconds: float = 0.20,
        min_confidence: float | None = None,
        min_margin: float | None = None,
        capture_dir: str | Path | None = None,
    ) -> None:
        if average_frames <= 0:
            raise RealModelError("average_frames must be positive")

        self.package = package or load_model_package()
        self.labels = load_labels(self.package.labels_path)
        self.preprocessing_config = json.loads(
            self.package.config_path.read_text(encoding="utf-8")
        )
        self.average_frames = int(average_frames)
        self.frame_interval_seconds = float(frame_interval_seconds)
        self.min_confidence = (
            settings.ml.real_min_confidence
            if min_confidence is None
            else float(min_confidence)
        )
        self.min_margin = (
            settings.ml.real_min_margin
            if min_margin is None
            else float(min_margin)
        )
        self.capture_dir = (
            Path(capture_dir).expanduser().resolve()
            if capture_dir is not None
            else settings.captures_dir / "real_runtime"
        )

        image_size = self.preprocessing_config.get("image_size", [224, 224])
        if isinstance(image_size, int):
            image_size = [image_size, image_size]
        self.image_size = [int(image_size[0]), int(image_size[1])]

        self.interpreter, self.backend = load_interpreter(self.package.model_path)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    def capture_average_prediction(self, camera: Any) -> RealPredictionResult:
        np = _load_numpy()
        Image = _load_pil_image()
        probabilities: list[Any] = []
        saved_frame = None

        started = time.perf_counter()

        for frame_number in range(self.average_frames):
            frame_rgb = capture_corrected_rgb_frame(camera)

            if saved_frame is None:
                saved_frame = frame_rgb.copy()

            probabilities.append(
                predict_probabilities(
                    interpreter=self.interpreter,
                    input_details=self.input_details,
                    output_details=self.output_details,
                    frame_rgb=frame_rgb,
                    image_size=self.image_size,
                )
            )

            if frame_number < self.average_frames - 1:
                time.sleep(self.frame_interval_seconds)

        if saved_frame is None:
            raise RealModelError("No camera frame was captured.")

        self.capture_dir.mkdir(parents=True, exist_ok=True)
        capture_path = self.capture_dir / (
            f"real_runtime_{datetime.now():%Y%m%d_%H%M%S_%f}.jpg"
        )
        Image.fromarray(saved_frame).save(capture_path, quality=95)

        average_probs = np.mean(np.stack(probabilities), axis=0)
        inference_ms = (time.perf_counter() - started) * 1000.0

        sorted_indexes = np.argsort(average_probs)[::-1]
        top3 = [
            {
                "label": self.labels.get(int(index), f"class_{int(index)}"),
                "confidence": float(average_probs[int(index)]),
            }
            for index in sorted_indexes[:3]
        ]

        if not top3:
            raise RealModelError("Model did not return any probabilities")

        predicted_category = str(top3[0]["label"])
        confidence = float(top3[0]["confidence"])
        margin = (
            confidence - float(top3[1]["confidence"])
            if len(top3) > 1
            else confidence
        )

        if predicted_category not in REAL_MODEL_CATEGORIES:
            raise RealModelError(f"Unsupported model category: {predicted_category}")

        rejection_reason = None
        if confidence < self.min_confidence:
            rejection_reason = (
                f"low_confidence:{confidence:.3f}<min:{self.min_confidence:.3f}"
            )
        elif margin < self.min_margin:
            rejection_reason = f"low_margin:{margin:.3f}<min:{self.min_margin:.3f}"

        accepted = rejection_reason is None
        recyclable = predicted_category in RECYCLABLE_CATEGORIES
        expected_side = "recyclable" if recyclable else "non_recyclable"

        return RealPredictionResult(
            category=predicted_category,
            label=predicted_category,
            confidence=round(confidence, 6),
            margin=round(float(margin), 6),
            accepted=accepted,
            rejectionReason=rejection_reason,
            expectedSide=expected_side,
            recyclable=recyclable,
            modelVersion=self.package.model_version,
            classificationSource="camera",
            inferenceBackend=self.backend,
            inferenceTimeMs=round(inference_ms, 3),
            imagePath=str(capture_path),
            top3=top3,
            rawOutput={
                "averageFrames": self.average_frames,
                "frameIntervalSeconds": self.frame_interval_seconds,
                "minConfidence": self.min_confidence,
                "minMargin": self.min_margin,
                "imageSize": self.image_size,
            },
        )


__all__ = [
    "REAL_MODEL_CATEGORIES",
    "RECYCLABLE_CATEGORIES",
    "NON_RECYCLABLE_CATEGORIES",
    "RealModelError",
    "RealModelPackage",
    "RealPredictionResult",
    "load_model_package",
    "load_interpreter",
    "load_labels",
    "softmax_if_needed",
    "preprocess_frame",
    "predict_probabilities",
    "capture_corrected_rgb_frame",
    "EfficientNetV2CameraClassifier",
]
