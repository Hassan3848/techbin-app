"""
Test TechBin left/right side detector without touching GPIO.

This test uses constructed ultrasonic readings and simulated sensor backends.

Run:
    PYTHONPATH=. python3 tests/test_side_detector.py
"""

from __future__ import annotations

from pprint import pprint

from app.config import LEFT_SIDE, RIGHT_SIDE
from app.sensors.pin_map import PIN_MAP, validate_pin_map
from app.sensors.side_detector import (
    DualUltrasonicSideDetector,
    SideDetectionConfig,
    detect_side_from_readings,
)
from app.sensors.ultrasonic import (
    SimulatedUltrasonicBackend,
    UltrasonicReading,
    build_sensor_from_pin_config,
)


def make_reading(
    *,
    name: str,
    role: str,
    distance_cm: float,
    valid: bool = True,
    fault_code: str | None = None,
) -> UltrasonicReading:
    return UltrasonicReading(
        sensorName=name,
        role=role,
        timestamp="2026-01-01T00:00:00.000000",
        distanceCm=distance_cm if valid else None,
        rawReadingsCm=[distance_cm] if valid else [],
        valid=valid,
        faultCode=fault_code,
        message="test reading" if valid else "invalid test reading",
        triggerGpio=1,
        echoGpio=2,
    )


def test_left_side_detected() -> None:
    print()
    print("========== Left Side Detected ==========")

    config = SideDetectionConfig(
        disturbance_threshold_cm=5.0,
        dominance_margin_cm=6.0,
    )

    result = detect_side_from_readings(
        left_baseline=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=45.0,
        ),
        left_current=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=30.0,
        ),
        right_baseline=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        right_current=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=44.0,
        ),
        config=config,
    )

    pprint(result.to_dict())

    assert result.valid is True
    assert result.detectedSide == LEFT_SIDE
    assert result.disposalSide == LEFT_SIDE
    assert result.faultCode is None

    print("PASS: left side detected")


def test_right_side_detected() -> None:
    print()
    print("========== Right Side Detected ==========")

    config = SideDetectionConfig(
        disturbance_threshold_cm=5.0,
        dominance_margin_cm=6.0,
    )

    result = detect_side_from_readings(
        left_baseline=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=45.0,
        ),
        left_current=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=44.0,
        ),
        right_baseline=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        right_current=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=28.0,
        ),
        config=config,
    )

    pprint(result.to_dict())

    assert result.valid is True
    assert result.detectedSide == RIGHT_SIDE
    assert result.disposalSide == RIGHT_SIDE
    assert result.faultCode is None

    print("PASS: right side detected")


def test_no_side_detected() -> None:
    print()
    print("========== No Side Detected ==========")

    config = SideDetectionConfig(
        disturbance_threshold_cm=5.0,
        dominance_margin_cm=6.0,
    )

    result = detect_side_from_readings(
        left_baseline=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=45.0,
        ),
        left_current=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=43.0,
        ),
        right_baseline=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        right_current=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=42.0,
        ),
        config=config,
    )

    pprint(result.to_dict())

    assert result.valid is False
    assert result.detectedSide == "unknown"
    assert result.disposalSide is None
    assert result.faultCode == "no_compartment_disturbance"

    print("PASS: no side detected")


def test_ambiguous_side_detected() -> None:
    print()
    print("========== Ambiguous Side Detected ==========")

    config = SideDetectionConfig(
        disturbance_threshold_cm=5.0,
        dominance_margin_cm=6.0,
    )

    result = detect_side_from_readings(
        left_baseline=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=45.0,
        ),
        left_current=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=30.0,
        ),
        right_baseline=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        right_current=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=32.0,
        ),
        config=config,
    )

    pprint(result.to_dict())

    assert result.valid is False
    assert result.detectedSide == "ambiguous"
    assert result.disposalSide is None
    assert result.faultCode == "ambiguous_compartment_disturbance"

    print("PASS: ambiguous side detected")


def test_both_disturbed_but_left_dominates() -> None:
    print()
    print("========== Both Disturbed But Left Dominates ==========")

    config = SideDetectionConfig(
        disturbance_threshold_cm=5.0,
        dominance_margin_cm=6.0,
    )

    result = detect_side_from_readings(
        left_baseline=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=45.0,
        ),
        left_current=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=20.0,
        ),
        right_baseline=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        right_current=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=36.0,
        ),
        config=config,
    )

    pprint(result.to_dict())

    assert result.valid is True
    assert result.detectedSide == LEFT_SIDE
    assert result.disposalSide == LEFT_SIDE
    assert "both_compartments_disturbed_but_left_dominated" in result.warnings

    print("PASS: both disturbed but left dominates")


def test_invalid_reading_rejected() -> None:
    print()
    print("========== Invalid Reading Rejected ==========")

    config = SideDetectionConfig(
        disturbance_threshold_cm=5.0,
        dominance_margin_cm=6.0,
    )

    result = detect_side_from_readings(
        left_baseline=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=45.0,
        ),
        left_current=make_reading(
            name="left_ultrasonic",
            role="left",
            distance_cm=0.0,
            valid=False,
            fault_code="ultrasonic_read_failed",
        ),
        right_baseline=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        right_current=make_reading(
            name="right_ultrasonic",
            role="right",
            distance_cm=45.0,
        ),
        config=config,
    )

    pprint(result.to_dict())

    assert result.valid is False
    assert result.detectedSide == "unknown"
    assert result.faultCode == "side_evidence_invalid"

    print("PASS: invalid reading rejected")


def test_stateful_dual_side_detector() -> None:
    print()
    print("========== Stateful Dual Side Detector ==========")

    validate_pin_map()

    left_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_left,
        enabled=True,
        backend=SimulatedUltrasonicBackend(
            sequence_cm=[
                45.0,
                30.0,
            ],
        ),
        samples=1,
    )

    right_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_right,
        enabled=True,
        backend=SimulatedUltrasonicBackend(
            sequence_cm=[
                45.0,
                44.0,
            ],
        ),
        samples=1,
    )

    detector = DualUltrasonicSideDetector(
        left_sensor=left_sensor,
        right_sensor=right_sensor,
        config=SideDetectionConfig(
            disturbance_threshold_cm=5.0,
            dominance_margin_cm=6.0,
        ),
    )

    detector.capture_baseline()
    result = detector.detect_once()

    pprint(result.to_dict())

    assert result.valid is True
    assert result.detectedSide == LEFT_SIDE
    assert result.disposalSide == LEFT_SIDE

    print("PASS: stateful dual side detector")


def main() -> None:
    test_left_side_detected()
    test_right_side_detected()
    test_no_side_detected()
    test_ambiguous_side_detected()
    test_both_disturbed_but_left_dominates()
    test_invalid_reading_rejected()
    test_stateful_dual_side_detector()

    print()
    print("All side detector tests passed.")


if __name__ == "__main__":
    main()
