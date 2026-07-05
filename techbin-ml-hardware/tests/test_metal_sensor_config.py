"""
Test TechBin metal sensor module without touching GPIO.

This test uses SimulatedMetalSensorBackend only.

Run:
    PYTHONPATH=. python3 tests/test_metal_sensor_config.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.metal_sensor import (
    MetalSensor,
    MetalSensorConfig,
    SimulatedMetalSensorBackend,
    build_metal_sensor_from_pin_config,
)
from app.sensors.pin_map import PIN_MAP, validate_pin_map


def test_disabled_sensor_result() -> None:
    print()
    print("========== Disabled Metal Sensor ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=False,
        active_low=False,
    )

    sensor = MetalSensor(
        config=config,
        backend=SimulatedMetalSensorBackend(fixed_signal=True),
    )

    reading = sensor.read_once()

    pprint(reading.to_dict())

    assert reading.valid is False
    assert reading.faultCode == "metal_sensor_not_enabled"
    assert reading.metalDetected is None

    print("PASS: disabled metal sensor")


def test_active_high_detection() -> None:
    print()
    print("========== Active HIGH Detection ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=True,
        active_low=False,
    )

    sensor = MetalSensor(
        config=config,
        backend=SimulatedMetalSensorBackend(fixed_signal=True),
    )

    reading = sensor.read_once()

    pprint(reading.to_dict())

    assert reading.valid is True
    assert reading.metalDetected is True

    print("PASS: active HIGH detection")


def test_active_low_detection() -> None:
    print()
    print("========== Active LOW Detection ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=True,
        active_low=True,
    )

    sensor = MetalSensor(
        config=config,
        backend=SimulatedMetalSensorBackend(fixed_signal=False),
    )

    reading = sensor.read_once()

    pprint(reading.to_dict())

    assert reading.valid is True
    assert reading.metalDetected is True

    print("PASS: active LOW detection")


def test_debounced_reading() -> None:
    print()
    print("========== Debounced Metal Reading ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=True,
        active_low=False,
        samples=5,
        sample_delay_seconds=0.0,
    )

    backend = SimulatedMetalSensorBackend(
        sequence=[True, False, True, True, False],
    )

    sensor = MetalSensor(
        config=config,
        backend=backend,
    )

    reading = sensor.read_debounced()

    pprint(reading.to_dict())

    assert reading.valid is True
    assert reading.metalDetected is True

    print("PASS: debounced reading")


def test_stuck_high_health() -> None:
    print()
    print("========== Stuck HIGH Health ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=True,
        active_low=False,
    )

    sensor = MetalSensor(
        config=config,
        backend=SimulatedMetalSensorBackend(fixed_signal=True),
    )

    health = sensor.check_signal_health(
        samples=5,
        sample_delay_seconds=0.0,
    )

    pprint(health.to_dict())

    assert health.ok is False
    assert health.faultCode == "metal_sensor_signal_stuck_high"

    print("PASS: stuck HIGH health")


def test_stuck_low_health() -> None:
    print()
    print("========== Stuck LOW Health ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=True,
        active_low=False,
    )

    sensor = MetalSensor(
        config=config,
        backend=SimulatedMetalSensorBackend(fixed_signal=False),
    )

    health = sensor.check_signal_health(
        samples=5,
        sample_delay_seconds=0.0,
    )

    pprint(health.to_dict())

    assert health.ok is False
    assert health.faultCode == "metal_sensor_signal_stuck_low"

    print("PASS: stuck LOW health")


def test_changing_signal_health() -> None:
    print()
    print("========== Changing Signal Health ==========")

    config = MetalSensorConfig(
        signal_gpio=21,
        enabled=True,
        active_low=False,
    )

    sensor = MetalSensor(
        config=config,
        backend=SimulatedMetalSensorBackend(
            sequence=[False, False, True, False, True, True],
        ),
    )

    health = sensor.check_signal_health(
        samples=6,
        sample_delay_seconds=0.0,
    )

    pprint(health.to_dict())

    assert health.ok is True
    assert health.faultCode is None

    print("PASS: changing signal health")


def test_build_from_pin_config() -> None:
    print()
    print("========== Build Metal Sensor From Pin Config ==========")

    validate_pin_map()

    sensor = build_metal_sensor_from_pin_config(
        PIN_MAP.metal_sensor,
        enabled=True,
        backend=SimulatedMetalSensorBackend(fixed_signal=True),
        samples=3,
    )

    reading = sensor.read_debounced()

    pprint(reading.to_dict())

    assert reading.valid is True
    assert reading.signalGpio == PIN_MAP.metal_sensor.signal_gpio

    print("PASS: build from pin config")


def main() -> None:
    test_disabled_sensor_result()
    test_active_high_detection()
    test_active_low_detection()
    test_debounced_reading()
    test_stuck_high_health()
    test_stuck_low_health()
    test_changing_signal_health()
    test_build_from_pin_config()

    print()
    print("All metal sensor config tests passed.")


if __name__ == "__main__":
    main()
