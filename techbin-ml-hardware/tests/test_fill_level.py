"""
Test TechBin fill-level capacity estimation.

This test does not touch GPIO.

Run:
    PYTHONPATH=. python3 tests/test_fill_level.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.fill_level import (
    FillLevelConfig,
    calculate_fill_percentage,
    capacity_level_from_percentage,
    default_left_fill_config,
    estimate_fill_level_from_distance,
    indicator_color_for_capacity,
)


def test_percentage_calculation() -> None:
    print()
    print("========== Fill Percentage Calculation ==========")

    config = FillLevelConfig(
        compartment_name="test_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    empty = calculate_fill_percentage(45.0, config)
    half = calculate_fill_percentage(25.0, config)
    full = calculate_fill_percentage(5.0, config)

    print("Empty percentage:", empty)
    print("Half percentage:", half)
    print("Full percentage:", full)

    assert empty == 0.0
    assert half == 50.0
    assert full == 100.0

    print("PASS: percentage calculation")


def test_capacity_levels_and_colors() -> None:
    print()
    print("========== Capacity Levels and Colors ==========")

    config = FillLevelConfig(
        compartment_name="test_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    cases = [
        (10.0, "low", "green"),
        (50.0, "half", "yellow"),
        (85.0, "full", "red"),
    ]

    for percentage, expected_level, expected_color in cases:
        level = capacity_level_from_percentage(percentage, config)
        color = indicator_color_for_capacity(level)

        print(percentage, "=>", level, "=>", color)

        assert level == expected_level
        assert color == expected_color

    print("PASS: capacity levels and colors")


def test_fill_result_low_half_full() -> None:
    print()
    print("========== Fill Result Low/Half/Full ==========")

    config = FillLevelConfig(
        compartment_name="test_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    low_result = estimate_fill_level_from_distance(40.0, config)
    half_result = estimate_fill_level_from_distance(25.0, config)
    full_result = estimate_fill_level_from_distance(8.0, config)

    pprint(low_result.to_dict())
    pprint(half_result.to_dict())
    pprint(full_result.to_dict())

    assert low_result.capacityLevel == "low"
    assert low_result.indicatorColor == "green"

    assert half_result.capacityLevel == "half"
    assert half_result.indicatorColor == "yellow"

    assert full_result.capacityLevel == "full"
    assert full_result.indicatorColor == "red"

    print("PASS: fill result low/half/full")


def test_missing_distance() -> None:
    print()
    print("========== Missing Distance ==========")

    config = default_left_fill_config()

    result = estimate_fill_level_from_distance(None, config)

    pprint(result.to_dict())

    assert result.valid is False
    assert result.capacityLevel == "unknown"
    assert result.indicatorColor == "off"
    assert result.faultCode == "fill_distance_missing"

    print("PASS: missing distance")


def main() -> None:
    test_percentage_calculation()
    test_capacity_levels_and_colors()
    test_fill_result_low_half_full()
    test_missing_distance()

    print()
    print("All fill-level tests passed.")


if __name__ == "__main__":
    main()
