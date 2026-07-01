"""
Test TechBin real dustbin capacity calibration.

This test does not touch real Arduino, GPIO, or serial ports.

Run:
    PYTHONPATH=. python3 tests/test_capacity_calibration.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.capacity_calibration import (
    get_techbin_capacity_calibration,
    techbin_left_fill_config,
    techbin_right_fill_config,
)
from app.sensors.fill_level import estimate_fill_level_from_ultrasonic
from app.sensors.ultrasonic import UltrasonicReading


def make_reading(sensor_name: str, distance_cm: float) -> UltrasonicReading:
    return UltrasonicReading(
        sensorName=sensor_name,
        role="capacity_calibration_test",
        timestamp="2026-01-01T00:00:00.000000",
        distanceCm=distance_cm,
        rawReadingsCm=[distance_cm],
        valid=True,
        faultCode=None,
        message="test reading",
        triggerGpio=-1,
        echoGpio=-1,
    )


def test_empty_distances_are_near_zero_fill() -> None:
    print()
    print("========== Capacity Calibration: Empty = 0% ==========")

    calibration = get_techbin_capacity_calibration()

    left_result = estimate_fill_level_from_ultrasonic(
        reading=make_reading(
            "left_ultrasonic",
            calibration.left_empty_distance_cm,
        ),
        config=techbin_left_fill_config(),
    )

    right_result = estimate_fill_level_from_ultrasonic(
        reading=make_reading(
            "right_ultrasonic",
            calibration.right_empty_distance_cm,
        ),
        config=techbin_right_fill_config(),
    )

    pprint(left_result.to_dict())
    pprint(right_result.to_dict())

    assert left_result.valid is True
    assert right_result.valid is True

    assert left_result.fillPercentage == 0.0
    assert right_result.fillPercentage == 0.0

    assert left_result.capacityLevel == "low"
    assert right_result.capacityLevel == "low"

    assert left_result.indicatorColor == "green"
    assert right_result.indicatorColor == "green"

    print("PASS: empty calibrated distances produce 0% fill")


def test_half_distances_are_half_fill() -> None:
    print()
    print("========== Capacity Calibration: Half = 50% ==========")

    calibration = get_techbin_capacity_calibration()

    left_half_distance = (
        calibration.left_empty_distance_cm + calibration.left_full_distance_cm
    ) / 2.0

    right_half_distance = (
        calibration.right_empty_distance_cm + calibration.right_full_distance_cm
    ) / 2.0

    left_result = estimate_fill_level_from_ultrasonic(
        reading=make_reading("left_ultrasonic", left_half_distance),
        config=techbin_left_fill_config(),
    )

    right_result = estimate_fill_level_from_ultrasonic(
        reading=make_reading("right_ultrasonic", right_half_distance),
        config=techbin_right_fill_config(),
    )

    pprint(left_result.to_dict())
    pprint(right_result.to_dict())

    assert left_result.valid is True
    assert right_result.valid is True

    assert 49.0 <= left_result.fillPercentage <= 51.0
    assert 49.0 <= right_result.fillPercentage <= 51.0

    assert left_result.capacityLevel == "half"
    assert right_result.capacityLevel == "half"

    assert left_result.indicatorColor == "yellow"
    assert right_result.indicatorColor == "yellow"

    print("PASS: half distances produce around 50% fill")


def test_full_distances_are_full_fill() -> None:
    print()
    print("========== Capacity Calibration: Full = 100% ==========")

    calibration = get_techbin_capacity_calibration()

    left_result = estimate_fill_level_from_ultrasonic(
        reading=make_reading("left_ultrasonic", calibration.left_full_distance_cm),
        config=techbin_left_fill_config(),
    )

    right_result = estimate_fill_level_from_ultrasonic(
        reading=make_reading("right_ultrasonic", calibration.right_full_distance_cm),
        config=techbin_right_fill_config(),
    )

    pprint(left_result.to_dict())
    pprint(right_result.to_dict())

    assert left_result.valid is True
    assert right_result.valid is True

    assert left_result.fillPercentage == 100.0
    assert right_result.fillPercentage == 100.0

    assert left_result.capacityLevel == "full"
    assert right_result.capacityLevel == "full"

    assert left_result.indicatorColor == "red"
    assert right_result.indicatorColor == "red"

    print("PASS: full calibrated distances produce 100% fill")


def main() -> None:
    test_empty_distances_are_near_zero_fill()
    test_half_distances_are_half_fill()
    test_full_distances_are_full_fill()

    print()
    print("All capacity calibration tests passed.")


if __name__ == "__main__":
    main()
