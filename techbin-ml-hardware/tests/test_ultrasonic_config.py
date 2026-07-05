"""
Test TechBin ultrasonic sensor module without touching GPIO.

This test uses SimulatedUltrasonicBackend only.

Run:
    PYTHONPATH=. python3 tests/test_ultrasonic_config.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.pin_map import PIN_MAP, get_ultrasonic_pin_configs, validate_pin_map
from app.sensors.ultrasonic import (
    SimulatedUltrasonicBackend,
    UltrasonicDistanceSensor,
    UltrasonicSensorConfig,
    build_sensor_from_pin_config,
)


def test_pin_map() -> None:
    print()
    print("========== Ultrasonic Pin Map ==========")

    validate_pin_map()

    pprint(PIN_MAP.to_dict())

    configs = get_ultrasonic_pin_configs()

    assert len(configs) == 3

    names = {config.name for config in configs}

    assert names == {
        "front_ultrasonic",
        "left_ultrasonic",
        "right_ultrasonic",
    }

    print("PASS: pin map")


def test_disabled_sensor_result() -> None:
    print()
    print("========== Disabled Sensor Result ==========")

    config = UltrasonicSensorConfig(
        name="test_ultrasonic",
        trigger_gpio=23,
        echo_gpio=24,
        role="test_role",
        enabled=False,
    )

    sensor = UltrasonicDistanceSensor(
        config=config,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=50.0),
    )

    reading = sensor.read_once()

    pprint(reading.to_dict())

    assert reading.valid is False
    assert reading.faultCode == "ultrasonic_not_enabled"
    assert reading.distanceCm is None

    print("PASS: disabled sensor result")


def test_enabled_single_reading() -> None:
    print()
    print("========== Enabled Single Reading ==========")

    config = UltrasonicSensorConfig(
        name="test_ultrasonic",
        trigger_gpio=23,
        echo_gpio=24,
        role="test_role",
        enabled=True,
    )

    sensor = UltrasonicDistanceSensor(
        config=config,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=75.5),
    )

    reading = sensor.read_once()

    pprint(reading.to_dict())

    assert reading.valid is True
    assert reading.faultCode is None
    assert reading.distanceCm == 75.5

    print("PASS: enabled single reading")


def test_median_filtered_reading() -> None:
    print()
    print("========== Median Filtered Reading ==========")

    config = UltrasonicSensorConfig(
        name="test_ultrasonic",
        trigger_gpio=23,
        echo_gpio=24,
        role="test_role",
        enabled=True,
        samples=5,
        sample_delay_seconds=0.0,
    )

    backend = SimulatedUltrasonicBackend(
        sequence_cm=[50.0, 51.0, 49.0, 200.0, 50.5],
    )

    sensor = UltrasonicDistanceSensor(
        config=config,
        backend=backend,
    )

    reading = sensor.read_filtered()

    pprint(reading.to_dict())

    assert reading.valid is True
    assert reading.distanceCm == 50.5

    print("PASS: median filtered reading")


def test_invalid_distance_rejection() -> None:
    print()
    print("========== Invalid Distance Rejection ==========")

    config = UltrasonicSensorConfig(
        name="test_ultrasonic",
        trigger_gpio=23,
        echo_gpio=24,
        role="test_role",
        enabled=True,
        min_distance_cm=2.0,
        max_distance_cm=400.0,
    )

    sensor = UltrasonicDistanceSensor(
        config=config,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=900.0),
    )

    reading = sensor.read_once()

    pprint(reading.to_dict())

    assert reading.valid is False
    assert reading.faultCode == "ultrasonic_distance_too_large"

    print("PASS: invalid distance rejection")


def test_build_from_pin_config() -> None:
    print()
    print("========== Build From Pin Config ==========")

    sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=123.0),
        samples=3,
    )

    reading = sensor.read_filtered()

    pprint(reading.to_dict())

    assert reading.sensorName == "front_ultrasonic"
    assert reading.role == "user_session_detection"
    assert reading.valid is True
    assert reading.distanceCm == 123.0

    print("PASS: build from pin config")


def main() -> None:
    test_pin_map()
    test_disabled_sensor_result()
    test_enabled_single_reading()
    test_median_filtered_reading()
    test_invalid_distance_rejection()
    test_build_from_pin_config()

    print()
    print("All ultrasonic config tests passed.")


if __name__ == "__main__":
    main()
