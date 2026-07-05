"""
Test TechBin dual-compartment capacity monitor without touching GPIO.

This test uses:
    - simulated ultrasonic backends
    - simulated capacity indicator backend

Run:
    PYTHONPATH=. python3 tests/test_capacity_monitor.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.capacity_indicator import (
    SimulatedCapacityIndicatorBackend,
    build_indicator_from_pin_config,
)
from app.sensors.capacity_monitor import (
    DualCapacityMonitor,
    build_default_left_capacity_monitor,
    build_default_right_capacity_monitor,
)
from app.sensors.fill_level import FillLevelConfig
from app.sensors.pin_map import PIN_MAP, validate_pin_map
from app.sensors.ultrasonic import (
    SimulatedUltrasonicBackend,
    build_sensor_from_pin_config,
)


def test_single_left_capacity_monitor_low_fill() -> None:
    print()
    print("========== Single Left Capacity Monitor: Low Fill ==========")

    validate_pin_map()

    ultrasonic = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_left,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=40.0),
        samples=3,
    )

    indicator_backend = SimulatedCapacityIndicatorBackend()

    indicator = build_indicator_from_pin_config(
        PIN_MAP.traffic_light_left,
        enabled=True,
        backend=indicator_backend,
    )

    fill_config = FillLevelConfig(
        compartment_name="left_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    monitor = build_default_left_capacity_monitor(
        ultrasonic_sensor=ultrasonic,
        indicator=indicator,
        fill_config=fill_config,
        update_indicator=True,
    )

    result = monitor.check_capacity()

    pprint(result.to_dict())

    assert result.valid is True
    assert result.fillLevel["capacityLevel"] == "low"
    assert result.fillLevel["indicatorColor"] == "green"
    assert result.indicatorState is not None
    assert result.indicatorState["activeColor"] == "green"

    print("PASS: single left low fill")


def test_single_right_capacity_monitor_full_fill() -> None:
    print()
    print("========== Single Right Capacity Monitor: Full Fill ==========")

    validate_pin_map()

    ultrasonic = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_right,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=8.0),
        samples=3,
    )

    indicator_backend = SimulatedCapacityIndicatorBackend()

    indicator = build_indicator_from_pin_config(
        PIN_MAP.traffic_light_right,
        enabled=True,
        backend=indicator_backend,
    )

    fill_config = FillLevelConfig(
        compartment_name="right_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    monitor = build_default_right_capacity_monitor(
        ultrasonic_sensor=ultrasonic,
        indicator=indicator,
        fill_config=fill_config,
        update_indicator=True,
    )

    result = monitor.check_capacity()

    pprint(result.to_dict())

    assert result.valid is True
    assert result.fillLevel["capacityLevel"] == "full"
    assert result.fillLevel["indicatorColor"] == "red"
    assert result.indicatorState is not None
    assert result.indicatorState["activeColor"] == "red"

    print("PASS: single right full fill")


def test_dual_capacity_monitor() -> None:
    print()
    print("========== Dual Capacity Monitor ==========")

    validate_pin_map()

    shared_indicator_backend = SimulatedCapacityIndicatorBackend()

    left_ultrasonic = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_left,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=40.0),
        samples=3,
    )

    right_ultrasonic = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_right,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=25.0),
        samples=3,
    )

    left_indicator = build_indicator_from_pin_config(
        PIN_MAP.traffic_light_left,
        enabled=True,
        backend=shared_indicator_backend,
    )

    right_indicator = build_indicator_from_pin_config(
        PIN_MAP.traffic_light_right,
        enabled=True,
        backend=shared_indicator_backend,
    )

    left_fill_config = FillLevelConfig(
        compartment_name="left_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    right_fill_config = FillLevelConfig(
        compartment_name="right_compartment",
        empty_distance_cm=45.0,
        full_distance_cm=5.0,
        low_threshold_percent=40.0,
        full_threshold_percent=80.0,
    )

    left_monitor = build_default_left_capacity_monitor(
        ultrasonic_sensor=left_ultrasonic,
        indicator=left_indicator,
        fill_config=left_fill_config,
    )

    right_monitor = build_default_right_capacity_monitor(
        ultrasonic_sensor=right_ultrasonic,
        indicator=right_indicator,
        fill_config=right_fill_config,
    )

    dual_monitor = DualCapacityMonitor(
        left_monitor=left_monitor,
        right_monitor=right_monitor,
    )

    result = dual_monitor.check_all()

    pprint(result.to_dict())

    assert result.overallValid is True
    assert result.left["fillLevel"]["capacityLevel"] == "low"
    assert result.left["indicatorState"]["activeColor"] == "green"

    assert result.right["fillLevel"]["capacityLevel"] == "half"
    assert result.right["indicatorState"]["activeColor"] == "yellow"

    print("PASS: dual capacity monitor")


def test_dual_capacity_monitor_with_invalid_sensor() -> None:
    print()
    print("========== Dual Capacity Monitor With Invalid Sensor ==========")

    validate_pin_map()

    shared_indicator_backend = SimulatedCapacityIndicatorBackend()

    left_ultrasonic = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_left,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=40.0),
        samples=3,
    )

    # Right reading is intentionally out of valid HC-SR04 range.
    right_ultrasonic = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_right,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=900.0),
        samples=3,
    )

    left_indicator = build_indicator_from_pin_config(
        PIN_MAP.traffic_light_left,
        enabled=True,
        backend=shared_indicator_backend,
    )

    right_indicator = build_indicator_from_pin_config(
        PIN_MAP.traffic_light_right,
        enabled=True,
        backend=shared_indicator_backend,
    )

    left_monitor = build_default_left_capacity_monitor(
        ultrasonic_sensor=left_ultrasonic,
        indicator=left_indicator,
    )

    right_monitor = build_default_right_capacity_monitor(
        ultrasonic_sensor=right_ultrasonic,
        indicator=right_indicator,
    )

    dual_monitor = DualCapacityMonitor(
        left_monitor=left_monitor,
        right_monitor=right_monitor,
    )

    result = dual_monitor.check_all()

    pprint(result.to_dict())

    assert result.overallValid is False
    assert result.left["valid"] is True
    assert result.right["valid"] is False
    assert len(result.faultCodes) >= 1

    print("PASS: dual capacity monitor with invalid sensor")


def main() -> None:
    test_single_left_capacity_monitor_low_fill()
    test_single_right_capacity_monitor_full_fill()
    test_dual_capacity_monitor()
    test_dual_capacity_monitor_with_invalid_sensor()

    print()
    print("All capacity monitor tests passed.")


if __name__ == "__main__":
    main()
