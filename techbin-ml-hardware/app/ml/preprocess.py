"""
Image preprocessing utilities for TechBin ML inference.

Current purpose:
    Prepare a clean production boundary for real TFLite model integration.

This module does not decide the waste class.
It only prepares camera images into model-ready input arrays.

Supported behavior:
    - validate image path
    - read image metadata
    - convert image to RGB
    - resize image to model input size
    - create batch tensor
    - support common normalization modes

Future use:
    TFLiteWasteClassifier in app/ml/infer.py will call this module before
    running actual model inference.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from app.logger import get_logger


logger = get_logger(__name__)


NormalizationMode = Literal[
    "none",
    "zero_to_one",
    "minus_one_to_one",
]


class ImagePreprocessError(RuntimeError):
    """Raised when image preprocessing fails."""


@dataclass(frozen=True)
class ImageMetadata:
    """
    Basic image metadata.
    """

    image_path: str
    width: int
    height: int
    mode: str
    format: str | None
    file_size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelInputSpec:
    """
    Model input configuration.

    For many transfer learning models:
        MobileNetV2 often uses 224x224
        InceptionV3 often uses 299x299

    Keep this configurable because your final selected model may differ.
    """

    width: int = 224
    height: int = 224
    channels: int = 3
    normalization: NormalizationMode = "zero_to_one"
    add_batch_dimension: bool = True
    dtype: str = "float32"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreprocessResult:
    """
    Result returned after preprocessing.

    image_array:
        Usually a numpy array with shape:
            (1, height, width, 3) if add_batch_dimension=True
            (height, width, 3) if add_batch_dimension=False
    """

    image_path: str
    input_shape: tuple[int, ...]
    input_dtype: str
    spec: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _import_pil_image():
    """
    Lazily import Pillow.

    This keeps module import safe even if Pillow is not installed yet.
    """

    try:
        from PIL import Image
    except ImportError as exc:
        raise ImagePreprocessError(
            "Pillow is required for image preprocessing. "
            "Install it with: sudo apt install -y python3-pil"
        ) from exc

    return Image


def _import_numpy():
    """
    Lazily import numpy.

    Picamera2 usually already depends on numpy, but this check gives a clear
    message if it is missing.
    """

    try:
        import numpy as np
    except ImportError as exc:
        raise ImagePreprocessError(
            "numpy is required for model input tensor creation. "
            "Install it with: sudo apt install -y python3-numpy"
        ) from exc

    return np


def validate_image_path(image_path: str | Path) -> Path:
    """
    Validate and normalize an image path.
    """

    if isinstance(image_path, Path):
        path = image_path.expanduser().resolve()

    elif isinstance(image_path, str):
        if image_path.strip() == "":
            raise ImagePreprocessError("image_path cannot be empty")

        path = Path(image_path).expanduser().resolve()

    else:
        raise ImagePreprocessError(
            f"image_path must be str or Path, got {type(image_path).__name__}"
        )

    if not path.exists():
        raise ImagePreprocessError(f"Image file does not exist: {path}")

    if not path.is_file():
        raise ImagePreprocessError(f"Image path is not a file: {path}")

    if path.stat().st_size <= 0:
        raise ImagePreprocessError(f"Image file is empty: {path}")

    return path


def read_image_metadata(image_path: str | Path) -> ImageMetadata:
    """
    Read basic image metadata without creating a model tensor.
    """

    path = validate_image_path(image_path)
    Image = _import_pil_image()

    try:
        with Image.open(path) as image:
            width, height = image.size

            return ImageMetadata(
                image_path=str(path),
                width=int(width),
                height=int(height),
                mode=str(image.mode),
                format=image.format,
                file_size_bytes=path.stat().st_size,
            )

    except Exception as exc:
        raise ImagePreprocessError(f"Failed to read image metadata: {path}") from exc


def _validate_model_input_spec(spec: ModelInputSpec) -> None:
    """
    Validate model input spec values.
    """

    if spec.width <= 0:
        raise ImagePreprocessError(f"Model input width must be positive, got {spec.width}")

    if spec.height <= 0:
        raise ImagePreprocessError(f"Model input height must be positive, got {spec.height}")

    if spec.channels != 3:
        raise ImagePreprocessError(
            f"Only RGB 3-channel input is currently supported, got {spec.channels}"
        )

    if spec.normalization not in ("none", "zero_to_one", "minus_one_to_one"):
        raise ImagePreprocessError(
            "normalization must be one of: none, zero_to_one, minus_one_to_one"
        )

    if spec.dtype not in ("float32", "uint8"):
        raise ImagePreprocessError("dtype must be one of: float32, uint8")


def load_and_preprocess_image(
    image_path: str | Path,
    spec: ModelInputSpec | None = None,
) -> tuple[Any, PreprocessResult]:
    """
    Load image and convert it to model-ready input.

    Returns:
        image_array:
            numpy array ready for model input.

        preprocess_result:
            metadata/debug information about preprocessing.
    """

    active_spec = spec or ModelInputSpec()
    _validate_model_input_spec(active_spec)

    path = validate_image_path(image_path)
    metadata = read_image_metadata(path)

    Image = _import_pil_image()
    np = _import_numpy()

    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image = image.resize((active_spec.width, active_spec.height))

            image_array = np.asarray(image)

            if active_spec.dtype == "float32":
                image_array = image_array.astype("float32")

                if active_spec.normalization == "zero_to_one":
                    image_array = image_array / 255.0

                elif active_spec.normalization == "minus_one_to_one":
                    image_array = (image_array / 127.5) - 1.0

                elif active_spec.normalization == "none":
                    pass

            elif active_spec.dtype == "uint8":
                image_array = image_array.astype("uint8")

                if active_spec.normalization != "none":
                    raise ImagePreprocessError(
                        "uint8 dtype only supports normalization='none'"
                    )

            if active_spec.add_batch_dimension:
                image_array = np.expand_dims(image_array, axis=0)

            result = PreprocessResult(
                image_path=str(path),
                input_shape=tuple(int(value) for value in image_array.shape),
                input_dtype=str(image_array.dtype),
                spec=active_spec.to_dict(),
                metadata=metadata.to_dict(),
            )

            logger.info(
                "Image preprocessed | image=%s | shape=%s | dtype=%s | normalization=%s",
                path,
                result.input_shape,
                result.input_dtype,
                active_spec.normalization,
            )

            return image_array, result

    except ImagePreprocessError:
        raise

    except Exception as exc:
        raise ImagePreprocessError(f"Failed to preprocess image: {path}") from exc


def preprocess_for_mobilenet_v2(image_path: str | Path) -> tuple[Any, PreprocessResult]:
    """
    Convenience preprocessing for MobileNetV2-style input.

    Input shape:
        1 x 224 x 224 x 3

    Normalization:
        minus_one_to_one

    Note:
        This is prepared for later testing. Final normalization must match the
        way your actual model was trained/exported.
    """

    spec = ModelInputSpec(
        width=224,
        height=224,
        channels=3,
        normalization="minus_one_to_one",
        add_batch_dimension=True,
        dtype="float32",
    )

    return load_and_preprocess_image(image_path, spec=spec)


def preprocess_for_inception_v3(image_path: str | Path) -> tuple[Any, PreprocessResult]:
    """
    Convenience preprocessing for InceptionV3-style input.

    Input shape:
        1 x 299 x 299 x 3

    Normalization:
        minus_one_to_one

    Note:
        Final normalization must match your training/export pipeline.
    """

    spec = ModelInputSpec(
        width=299,
        height=299,
        channels=3,
        normalization="minus_one_to_one",
        add_batch_dimension=True,
        dtype="float32",
    )

    return load_and_preprocess_image(image_path, spec=spec)


__all__ = [
    "NormalizationMode",
    "ImagePreprocessError",
    "ImageMetadata",
    "ModelInputSpec",
    "PreprocessResult",
    "validate_image_path",
    "read_image_metadata",
    "load_and_preprocess_image",
    "preprocess_for_mobilenet_v2",
    "preprocess_for_inception_v3",
]
