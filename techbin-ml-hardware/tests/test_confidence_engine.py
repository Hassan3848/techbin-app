"""
Test TechBin confidence engine.

Run from project root:
    PYTHONPATH=. python3 tests/test_confidence_engine.py
"""

from __future__ import annotations

from pprint import pprint

from app.engine.confidence_engine import evaluate_event_confidence
from app.engine.disposal_validator import validate_disposal


def run_case(
    case_name: str,
    predicted_class: str,
    confidence: float,
    disposal_side: str,
    expected_accepted: bool,
    *,
    metal_detected=None,
    compartment_confirmed=None,
    require_compartment_confirmation=False,
) -> None:
    validation = validate_disposal(
        predicted_class=predicted_class,
        confidence=confidence,
        disposal_side=disposal_side,
    )

    decision = evaluate_event_confidence(
        validation,
        image_captured=True,
        session_triggered=True,
        compartment_confirmed=compartment_confirmed,
        metal_detected=metal_detected,
        require_session_trigger=False,
        require_compartment_confirmation=require_compartment_confirmation,
    )

    print()
    print(f"========== Case: {case_name} ==========")
    pprint(decision.to_dict())

    assert decision.is_event_accepted is expected_accepted

    print(f"PASS: {case_name}")


def main() -> None:
    run_case(
        case_name="plastic_high_confidence_accept",
        predicted_class="plastic",
        confidence=0.91,
        disposal_side="right",
        expected_accepted=True,
    )

    run_case(
        case_name="plastic_low_confidence_reject",
        predicted_class="plastic",
        confidence=0.40,
        disposal_side="right",
        expected_accepted=False,
    )

    run_case(
        case_name="metal_with_sensor_support_accept",
        predicted_class="metal",
        confidence=0.91,
        disposal_side="right",
        expected_accepted=True,
        metal_detected=True,
    )

    run_case(
        case_name="metal_without_sensor_support_accept_with_warning",
        predicted_class="metal",
        confidence=0.91,
        disposal_side="right",
        expected_accepted=True,
        metal_detected=False,
    )

    run_case(
        case_name="future_compartment_required_but_missing_reject",
        predicted_class="trash",
        confidence=0.88,
        disposal_side="left",
        expected_accepted=False,
        compartment_confirmed=False,
        require_compartment_confirmation=True,
    )

    run_case(
        case_name="future_compartment_required_and_confirmed_accept",
        predicted_class="trash",
        confidence=0.88,
        disposal_side="left",
        expected_accepted=True,
        compartment_confirmed=True,
        require_compartment_confirmation=True,
    )

    print()
    print("All confidence engine tests passed.")


if __name__ == "__main__":
    main()
