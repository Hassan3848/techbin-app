"""
Test the TechBin central EventProcessor.

This test uses:
    - latest existing captured image
    - mock ML classifier
    - disposal validator
    - payload builder
    - local event logger

Run from project root:
    PYTHONPATH=. python3 tests/test_event_processor.py
"""

from __future__ import annotations

from pathlib import Path
from pprint import pprint

from app.engine.event_processor import process_disposal_event
from app.ml.infer import create_mock_classifier


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURES_DIR = PROJECT_ROOT / "captures"


def get_latest_image() -> Path:
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


def run_case(
    case_name: str,
    predicted_class: str,
    confidence: float,
    disposal_side: str,
    expected_correct: bool,
    expected_accepted: bool,
) -> None:
    image_path = get_latest_image()

    classifier = create_mock_classifier(
        predicted_class=predicted_class,
        confidence=confidence,
    )

    result = process_disposal_event(
        disposal_side=disposal_side,
        image_path=image_path,
        classifier=classifier,
        source=f"test_event_processor_{case_name}",
        log_prefix=f"test_event_processor_{case_name}",
    )

    payload = result.payload

    print()
    print(f"========== Case: {case_name} ==========")
    pprint(payload)
    print("Log path:", result.log_path)

    assert payload["predictedClass"] == predicted_class
    assert payload["disposalSide"] == disposal_side
    assert payload["isCorrectDisposal"] is expected_correct
    assert payload["isEventAccepted"] is expected_accepted
    assert Path(result.log_path).exists()

    print(f"PASS: {case_name}")


def main() -> None:
    run_case(
        case_name="plastic_right_correct",
        predicted_class="plastic",
        confidence=0.91,
        disposal_side="right",
        expected_correct=True,
        expected_accepted=True,
    )

    run_case(
        case_name="plastic_left_incorrect",
        predicted_class="plastic",
        confidence=0.91,
        disposal_side="left",
        expected_correct=False,
        expected_accepted=True,
    )

    run_case(
        case_name="trash_left_correct",
        predicted_class="trash",
        confidence=0.88,
        disposal_side="left",
        expected_correct=True,
        expected_accepted=True,
    )

    run_case(
        case_name="metal_low_confidence_rejected",
        predicted_class="metal",
        confidence=0.40,
        disposal_side="right",
        expected_correct=True,
        expected_accepted=False,
    )

    print()
    print("All EventProcessor tests passed.")


if __name__ == "__main__":
    main()
