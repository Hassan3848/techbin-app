"""
Manual production runner for TechBin device runtime.

This runner is used before real ML inference and real sensors are connected.

Current purpose:
    - manually provide predicted class
    - manually provide confidence
    - manually provide disposal side
    - use EventProcessor as the central runtime pipeline

Flow:
    1. Get predicted class manually
    2. Get confidence manually
    3. Get disposal side manually
    4. Create mock classifier from manual prediction
    5. EventProcessor captures image or uses provided image
    6. EventProcessor runs inference
    7. EventProcessor validates disposal
    8. EventProcessor builds payload
    9. EventProcessor saves JSON log

Run from project root:
    python3 -m app.main_manual

Non-interactive examples:
    python3 -m app.main_manual --predicted-class plastic --confidence 0.91 --disposal-side right

    python3 -m app.main_manual --predicted-class trash --confidence 0.88 --disposal-side left

    python3 -m app.main_manual --predicted-class plastic --confidence 0.91 --disposal-side left
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.camera.capture import CameraCaptureError
from app.config import ensure_runtime_directories
from app.engine.disposal_validator import (
    DisposalValidationError,
    normalize_disposal_side,
    validate_confidence,
)
from app.engine.event_processor import (
    EventProcessingError,
    EventProcessingResult,
    EventProcessor,
)
from app.logger import get_logger
from app.ml.infer import InferenceError, create_mock_classifier
from app.ml.labels import VALID_WASTE_CLASSES, WasteLabelError, normalize_waste_class
from app.telemetry.payloads import PayloadBuildError
from app.utils.event_logger import EventLogError


logger = get_logger(__name__)


VALID_SIDE_TEXT = "left/right"


def _build_arg_parser() -> argparse.ArgumentParser:
    """
    Build command-line argument parser.
    """

    parser = argparse.ArgumentParser(
        description="Run one manual TechBin disposal event through EventProcessor."
    )

    parser.add_argument(
        "--predicted-class",
        type=str,
        default=None,
        help="Manual predicted class: cardboard/glass/metal/paper/plastic/trash",
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="Manual prediction confidence from 0.0 to 1.0",
    )

    parser.add_argument(
        "--disposal-side",
        type=str,
        default=None,
        help="Actual disposal side: left or right",
    )

    parser.add_argument(
        "--image-path",
        type=str,
        default=None,
        help="Use an existing image instead of capturing a new one",
    )

    parser.add_argument(
        "--capture-prefix",
        type=str,
        default="manual_event",
        help="Filename prefix for captured image",
    )

    parser.add_argument(
        "--source",
        type=str,
        default="main_manual",
        help="Payload source field",
    )

    parser.add_argument(
        "--log-prefix",
        type=str,
        default="manual_event",
        help="Filename prefix for saved JSON event log",
    )

    return parser


def _prompt_waste_class() -> str:
    """
    Prompt until a valid waste class is entered.
    """

    allowed = "/".join(VALID_WASTE_CLASSES)

    while True:
        value = input(f"Enter predicted class ({allowed}): ").strip()

        try:
            return normalize_waste_class(value)
        except WasteLabelError as exc:
            print(f"Invalid class: {exc}")


def _prompt_confidence() -> float:
    """
    Prompt until a valid confidence score is entered.
    """

    while True:
        value = input("Enter confidence (0.0 to 1.0, example 0.91): ").strip()

        try:
            return validate_confidence(value)
        except DisposalValidationError as exc:
            print(f"Invalid confidence: {exc}")


def _prompt_disposal_side() -> str:
    """
    Prompt until a valid disposal side is entered.
    """

    while True:
        value = input(f"Enter disposal side ({VALID_SIDE_TEXT}): ").strip()

        try:
            return normalize_disposal_side(value)
        except DisposalValidationError as exc:
            print(f"Invalid disposal side: {exc}")


def _resolve_predicted_class(value: str | None) -> str:
    """
    Use CLI value or prompt for waste class.
    """

    if value is None:
        return _prompt_waste_class()

    return normalize_waste_class(value)


def _resolve_confidence(value: float | None) -> float:
    """
    Use CLI value or prompt for confidence.
    """

    if value is None:
        return _prompt_confidence()

    return validate_confidence(value)


def _resolve_disposal_side(value: str | None) -> str:
    """
    Use CLI value or prompt for disposal side.
    """

    if value is None:
        return _prompt_disposal_side()

    return normalize_disposal_side(value)


def _resolve_image_path(value: str | None) -> Path | None:
    """
    Resolve optional image path.

    If no image path is provided, EventProcessor will capture a fresh image.
    """

    if value is None or value.strip() == "":
        return None

    image_path = Path(value).expanduser().resolve()

    if not image_path.exists():
        raise FileNotFoundError(f"Provided image path does not exist: {image_path}")

    if not image_path.is_file():
        raise FileNotFoundError(f"Provided image path is not a file: {image_path}")

    return image_path


def _print_result(result: EventProcessingResult) -> None:
    """
    Print clean final result for demo/debugging.
    """

    payload = result.payload

    print()
    print("========== TechBin Manual Event Result ==========")
    print(f"Predicted class       : {payload['predictedClass']}")
    print(f"Recyclability         : {payload['recyclability']}")
    print(f"Confidence            : {payload['confidence']}")
    print(f"Disposal side         : {payload['disposalSide']}")
    print(f"Expected side         : {payload['expectedSide']}")
    print(f"Correct disposal      : {payload['isCorrectDisposal']}")
    print(f"Confidence accepted   : {payload['isConfidenceAccepted']}")
    print(f"Event accepted        : {payload['isEventAccepted']}")
    print(f"Rejection reason      : {payload['rejectionReason']}")
    print(f"Model name            : {payload.get('modelName')}")
    print(f"Inference time ms     : {payload.get('inferenceTimeMs')}")
    print(f"Captured now          : {result.was_captured_now}")
    print(f"Image path            : {payload['imagePath']}")
    print(f"Saved JSON log        : {result.log_path}")
    print("=================================================")

    print()
    print("Full payload:")
    print(json.dumps(payload, indent=2))


def run_manual_flow(args: argparse.Namespace) -> EventProcessingResult:
    """
    Run one complete manual disposal event flow using EventProcessor.
    """

    ensure_runtime_directories()

    predicted_class = _resolve_predicted_class(args.predicted_class)
    confidence = _resolve_confidence(args.confidence)
    disposal_side = _resolve_disposal_side(args.disposal_side)
    image_path = _resolve_image_path(args.image_path)

    classifier = create_mock_classifier(
        predicted_class=predicted_class,
        confidence=confidence,
    )

    processor = EventProcessor(
        classifier=classifier,
        source=args.source,
        capture_prefix=args.capture_prefix,
        log_prefix=args.log_prefix,
    )

    result = processor.process_disposal_event(
        disposal_side=disposal_side,
        image_path=image_path,
    )

    logger.info(
        "Manual EventProcessor flow completed | class=%s | confidence=%.3f | side=%s | expected=%s | correct=%s | accepted=%s",
        result.payload["predictedClass"],
        result.payload["confidence"],
        result.payload["disposalSide"],
        result.payload["expectedSide"],
        result.payload["isCorrectDisposal"],
        result.payload["isEventAccepted"],
    )

    _print_result(result)

    return result


def main() -> int:
    """
    CLI entry point.
    """

    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        run_manual_flow(args)
        return 0

    except KeyboardInterrupt:
        print()
        print("Manual event cancelled by user.")
        logger.warning("Manual event cancelled by user")
        return 130

    except (
        CameraCaptureError,
        DisposalValidationError,
        WasteLabelError,
        InferenceError,
        PayloadBuildError,
        EventLogError,
        EventProcessingError,
        FileNotFoundError,
    ) as exc:
        print()
        print(f"Manual event failed: {exc}")
        logger.error("Manual event failed: %s", exc)
        return 1

    except Exception as exc:
        print()
        print(f"Unexpected manual event failure: {exc}")
        logger.exception("Unexpected manual event failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
