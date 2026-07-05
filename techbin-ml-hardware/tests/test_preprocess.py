"""
Test TechBin image preprocessing utilities.

This test uses the latest captured .jpg image from captures/.

Run from project root:
    PYTHONPATH=. python3 tests/test_preprocess.py
"""

from __future__ import annotations

from pathlib import Path
from pprint import pprint

from app.ml.preprocess import (
    ModelInputSpec,
    load_and_preprocess_image,
    preprocess_for_inception_v3,
    preprocess_for_mobilenet_v2,
    read_image_metadata,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURES_DIR = PROJECT_ROOT / "captures"


def get_latest_image() -> Path:
    """
    Return the latest .jpg image from captures/.
    """

    images = sorted(
        CAPTURES_DIR.glob("*.jpg"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not images:
        raise FileNotFoundError(
            f"No .jpg images found in {CAPTURES_DIR}. Capture an image first."
        )

    return images[0]


def test_metadata(image_path: Path) -> None:
    """
    Test image metadata reading.
    """

    metadata = read_image_metadata(image_path)

    print()
    print("========== Image Metadata ==========")
    pprint(metadata.to_dict())

    assert metadata.width > 0
    assert metadata.height > 0
    assert metadata.file_size_bytes > 0
    assert metadata.format is not None

    print("PASS: metadata")


def test_default_preprocess(image_path: Path) -> None:
    """
    Test default preprocessing.

    Expected:
        shape = (1, 224, 224, 3)
        dtype = float32
        values between 0.0 and 1.0
    """

    image_array, result = load_and_preprocess_image(image_path)

    print()
    print("========== Default Preprocess ==========")
    pprint(result.to_dict())
    print("Min:", float(image_array.min()))
    print("Max:", float(image_array.max()))

    assert image_array.shape == (1, 224, 224, 3)
    assert str(image_array.dtype) == "float32"
    assert float(image_array.min()) >= 0.0
    assert float(image_array.max()) <= 1.0

    print("PASS: default preprocess")


def test_mobilenet_v2_preprocess(image_path: Path) -> None:
    """
    Test MobileNetV2-style preprocessing.

    Expected:
        shape = (1, 224, 224, 3)
        dtype = float32
        values between -1.0 and 1.0
    """

    image_array, result = preprocess_for_mobilenet_v2(image_path)

    print()
    print("========== MobileNetV2 Preprocess ==========")
    pprint(result.to_dict())
    print("Min:", float(image_array.min()))
    print("Max:", float(image_array.max()))

    assert image_array.shape == (1, 224, 224, 3)
    assert str(image_array.dtype) == "float32"
    assert float(image_array.min()) >= -1.0
    assert float(image_array.max()) <= 1.0
    assert result.spec["normalization"] == "minus_one_to_one"

    print("PASS: MobileNetV2 preprocess")


def test_inception_v3_preprocess(image_path: Path) -> None:
    """
    Test InceptionV3-style preprocessing.

    Expected:
        shape = (1, 299, 299, 3)
        dtype = float32
        values between -1.0 and 1.0
    """

    image_array, result = preprocess_for_inception_v3(image_path)

    print()
    print("========== InceptionV3 Preprocess ==========")
    pprint(result.to_dict())
    print("Min:", float(image_array.min()))
    print("Max:", float(image_array.max()))

    assert image_array.shape == (1, 299, 299, 3)
    assert str(image_array.dtype) == "float32"
    assert float(image_array.min()) >= -1.0
    assert float(image_array.max()) <= 1.0
    assert result.spec["normalization"] == "minus_one_to_one"

    print("PASS: InceptionV3 preprocess")


def test_custom_uint8_preprocess(image_path: Path) -> None:
    """
    Test uint8 preprocessing for models that expect raw image bytes.

    Expected:
        shape = (1, 128, 128, 3)
        dtype = uint8
        values between 0 and 255
    """

    spec = ModelInputSpec(
        width=128,
        height=128,
        channels=3,
        normalization="none",
        add_batch_dimension=True,
        dtype="uint8",
    )

    image_array, result = load_and_preprocess_image(image_path, spec=spec)

    print()
    print("========== Custom uint8 Preprocess ==========")
    pprint(result.to_dict())
    print("Min:", int(image_array.min()))
    print("Max:", int(image_array.max()))

    assert image_array.shape == (1, 128, 128, 3)
    assert str(image_array.dtype) == "uint8"
    assert int(image_array.min()) >= 0
    assert int(image_array.max()) <= 255

    print("PASS: custom uint8 preprocess")


def main() -> None:
    image_path = get_latest_image()

    print("Using image:", image_path)

    test_metadata(image_path)
    test_default_preprocess(image_path)
    test_mobilenet_v2_preprocess(image_path)
    test_inception_v3_preprocess(image_path)
    test_custom_uint8_preprocess(image_path)

    print()
    print("All preprocessing tests passed.")


if __name__ == "__main__":
    main()
