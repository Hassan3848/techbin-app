"""
TechBin device runtime entry point.

Current stage:
    This is a safe mock-runtime mode before real sensors and real model are connected.

Current flow:
    1. Wait for Enter key or CLI trigger
    2. Capture image from Raspberry Pi Camera
    3. Run mock ML inference
    4. Use manual disposal side input
    5. Process event through EventProcessor
    6. Save JSON event log

Future flow:
    1. User detected by front ultrasonic sensor
    2. Capture image
    3. Run real TFLite model inference
    4. Detect left/right compartment disturbance
    5. Validate disposal
    6. Save event log
    7. Sync telemetry
    8. Trigger audio/LED feedback
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import NoReturn

from app.camera.capture import CameraCaptureError
from app.config import ensure_runtime_directories
from app.engine.disposal_validator import DisposalValidationError, normalize_disposal_side
from app.engine.event_processor import EventProcessingError, EventProcessor
from app.logger import get_logger
from app.ml.infer import InferenceError, create_mock_classifier
from app.ml.labels import WasteLabelError, normalize_waste_class
from app.telemetry.payloads import PayloadBuildError
from app.utils.event_logger import EventLogError


logger = get_logger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run TechBin device runtime in safe mock mode."
    )

    parser.add_argument(
        "--mock-class",
        type=str,
        default="plastic",
        help="Mock ML class: cardboard/glass/metal/paper/plastic/trash",
    )

    parser.add_argument(
        "--mock-confidence",
        type=float,
        default=0.91,
        help="Mock ML confidence from 0.0 to 1.0",
    )

    parser.add_argument(
        "--disposal-side",
        type=str,
        default=None,
        help="Manual disposal side for one-shot mode: left/right",
    )

    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running multiple manual-trigger events.",
    )

    parser.add_argument(
        "--randomize",
        action="store_true",
        help="Randomize mock ML class/confidence for testing.",
    )

    parser.add_argument(
        "--source",
        type=str,
        default="main_runtime_mock",
        help="Payload source field.",
    )

    parser.add_argument(
        "--capture-prefix",
        type=str,
        default="runtime_event",
        help="Filename prefix for captured images.",
    )

    parser.add_argument(
        "--log-prefix",
        type=str,
        default="runtime_event",
        help="Filename prefix for event JSON logs.",
    )

    return parser


def _prompt_disposal_side() -> str:
    while True:
        value = input("Enter disposal side (left/right), or q to quit: ").strip()

        if value.lower() in {"q", "quit", "exit"}:
            raise KeyboardInterrupt

        try:
            return normalize_disposal_side(value)
        except DisposalValidationError as exc:
            print(f"Invalid disposal side: {exc}")


def _print_event_summary(result) -> None:
    payload = result.payload

    print()
    print("========== TechBin Runtime Event ==========")
    print(f"Predicted class       : {payload['predictedClass']}")
    print(f"Recyclability         : {payload['recyclability']}")
    print(f"Confidence            : {payload['confidence']}")
    print(f"Disposal side         : {payload['disposalSide']}")
    print(f"Expected side         : {payload['expectedSide']}")
    print(f"Correct disposal      : {payload['isCorrectDisposal']}")
    print(f"Event accepted        : {payload['isEventAccepted']}")
    print(f"Rejection reason      : {payload['rejectionReason']}")
    print(f"Image path            : {result.image_path}")
    print(f"JSON log              : {result.log_path}")
    print("===========================================")
    print()


def _process_one_event(processor: EventProcessor, disposal_side: str) -> None:
    result = processor.process_disposal_event(disposal_side=disposal_side)
    _print_event_summary(result)


def _run_one_shot(args: argparse.Namespace, processor: EventProcessor) -> int:
    disposal_side = args.disposal_side

    if disposal_side is None:
        print("No --disposal-side provided, asking manually.")
        disposal_side = _prompt_disposal_side()
    else:
        disposal_side = normalize_disposal_side(disposal_side)

    _process_one_event(processor, disposal_side)
    return 0


def _run_loop(args: argparse.Namespace, processor: EventProcessor) -> NoReturn:
    print()
    print("TechBin mock runtime loop started.")
    print("Press Enter to simulate a disposal event.")
    print("Type q at disposal-side prompt to quit.")
    print()

    while True:
        input("Press Enter when a user disposal event should be simulated... ")
        disposal_side = _prompt_disposal_side()
        _process_one_event(processor, disposal_side)


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        ensure_runtime_directories()

        mock_class = normalize_waste_class(args.mock_class)

        classifier = create_mock_classifier(
            predicted_class=mock_class,
            confidence=args.mock_confidence,
            randomize=args.randomize,
        )

        processor = EventProcessor(
            classifier=classifier,
            source=args.source,
            capture_prefix=args.capture_prefix,
            log_prefix=args.log_prefix,
        )

        logger.info(
            "Starting TechBin runtime mock mode | class=%s | confidence=%.3f | randomize=%s",
            mock_class,
            args.mock_confidence,
            args.randomize,
        )

        if args.loop:
            _run_loop(args, processor)

        return _run_one_shot(args, processor)

    except KeyboardInterrupt:
        print()
        print("Runtime stopped by user.")
        logger.warning("Runtime stopped by user")
        return 130

    except (
        CameraCaptureError,
        DisposalValidationError,
        WasteLabelError,
        InferenceError,
        PayloadBuildError,
        EventLogError,
        EventProcessingError,
    ) as exc:
        print()
        print(f"Runtime failed: {exc}")
        logger.error("Runtime failed: %s", exc)
        return 1

    except Exception as exc:
        print()
        print(f"Unexpected runtime failure: {exc}")
        logger.exception("Unexpected runtime failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
