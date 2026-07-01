"""
Test TechBin front ultrasonic session detector without touching GPIO.

This test uses simulated ultrasonic backend only.

Run:
    PYTHONPATH=. python3 tests/test_session_detector.py
"""

from __future__ import annotations

from pprint import pprint

from app.sensors.pin_map import PIN_MAP, validate_pin_map
from app.sensors.session_detector import FrontSessionDetector, SessionDetectorConfig
from app.sensors.ultrasonic import (
    SimulatedUltrasonicBackend,
    build_sensor_from_pin_config,
)


def test_idle_when_far() -> None:
    print()
    print("========== Session Detector: Idle When Far ==========")

    validate_pin_map()

    front_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=100.0),
        samples=3,
    )

    detector = FrontSessionDetector(
        front_sensor,
        config=SessionDetectorConfig(
            presence_threshold_cm=35.0,
            stable_presence_reads=2,
            stable_absence_reads=3,
        ),
    )

    result = detector.update()

    pprint(result.to_dict())

    assert result.valid is True
    assert result.presenceDetected is False
    assert result.sessionActive is False
    assert result.sessionStarted is False
    assert result.state == "idle"

    print("PASS: idle when far")


def test_session_starts_after_stable_presence() -> None:
    print()
    print("========== Session Starts After Stable Presence ==========")

    front_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=SimulatedUltrasonicBackend(
            sequence_cm=[25.0, 24.0, 23.0],
        ),
        samples=1,
    )

    detector = FrontSessionDetector(
        front_sensor,
        config=SessionDetectorConfig(
            presence_threshold_cm=35.0,
            stable_presence_reads=2,
            stable_absence_reads=3,
        ),
    )

    result_1 = detector.update()
    result_2 = detector.update()

    pprint(result_1.to_dict())
    pprint(result_2.to_dict())

    assert result_1.state == "presence_candidate"
    assert result_1.sessionStarted is False

    assert result_2.state == "active"
    assert result_2.sessionStarted is True
    assert result_2.sessionActive is True

    print("PASS: session starts after stable presence")


def test_session_ends_after_stable_absence() -> None:
    print()
    print("========== Session Ends After Stable Absence ==========")

    front_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=SimulatedUltrasonicBackend(
            sequence_cm=[
                25.0,
                24.0,
                100.0,
                110.0,
                120.0,
            ],
        ),
        samples=1,
    )

    detector = FrontSessionDetector(
        front_sensor,
        config=SessionDetectorConfig(
            presence_threshold_cm=35.0,
            stable_presence_reads=2,
            stable_absence_reads=3,
        ),
    )

    start_candidate = detector.update()
    started = detector.update()
    ending_1 = detector.update()
    ending_2 = detector.update()
    ended = detector.update()

    pprint(start_candidate.to_dict())
    pprint(started.to_dict())
    pprint(ending_1.to_dict())
    pprint(ending_2.to_dict())
    pprint(ended.to_dict())

    assert started.sessionStarted is True
    assert started.sessionActive is True

    assert ending_1.state == "ending_candidate"
    assert ending_1.sessionActive is True

    assert ending_2.state == "ending_candidate"
    assert ending_2.sessionActive is True

    assert ended.state == "ended"
    assert ended.sessionEnded is True
    assert ended.sessionActive is False

    print("PASS: session ends after stable absence")


def test_invalid_front_sensor_reading() -> None:
    print()
    print("========== Invalid Front Sensor Reading ==========")

    # Distance 900cm is outside the ultrasonic valid max range.
    front_sensor = build_sensor_from_pin_config(
        PIN_MAP.ultrasonic_front,
        enabled=True,
        backend=SimulatedUltrasonicBackend(fixed_distance_cm=900.0),
        samples=3,
    )

    detector = FrontSessionDetector(front_sensor)

    result = detector.update()

    pprint(result.to_dict())

    assert result.valid is False
    assert result.state == "fault"
    assert result.faultCode is not None

    print("PASS: invalid front sensor reading")


def main() -> None:
    test_idle_when_far()
    test_session_starts_after_stable_presence()
    test_session_ends_after_stable_absence()
    test_invalid_front_sensor_reading()

    print()
    print("All session detector tests passed.")


if __name__ == "__main__":
    main()
